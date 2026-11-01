"""Run JSON-schema constrained chat-completion style requests.

This generic runner can be reused for:
- code-change fact extraction
- release-note alignment evaluation
- other prompt + schema experiments
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Dict, Iterator, List

import requests


ACTIVE_API_KEY = ""

DEFAULT_API_URL = "https://api.deepseek.com/chat/completions"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run JSON-schema chat completion requests")
    parser.add_argument("--requests-path", required=True, help="JSONL file containing system_prompt/user_prompt/schema_path")
    parser.add_argument("--output-dir", required=True, help="Directory to store raw outputs, parsed outputs, and status logs")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Chat completions endpoint")
    parser.add_argument("--model", default="deepseek-chat", help="Model name")
    parser.add_argument("--temperature", type=float, default=0.1, help="Sampling temperature")
    parser.add_argument("--max-tokens", type=int, default=8192, help="Maximum tokens in model response")
    parser.add_argument("--max-retries", type=int, default=4, help="Maximum retries per sample")
    parser.add_argument("--sleep-seconds", type=float, default=0.8, help="Delay between successful calls")
    parser.add_argument("--timeout", type=int, default=180, help="HTTP timeout in seconds")
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY", help="Environment variable containing the API key (never pass credentials on the command line)")
    parser.add_argument("--max-concurrency", type=int, default=1, help="Maximum concurrent API requests")
    parser.add_argument("--max-samples", type=int, default=None, help="Optional cap for smoke testing")
    parser.add_argument("--resume", action="store_true", help="Skip rows already completed")
    parser.add_argument("--disable-thinking", action="store_true", help="Add enable_thinking=false to payload (required for Qwen3 non-streaming)")
    parser.add_argument("--id-field", default="sample_id", help="Request row id field used for status tracking")
    parser.add_argument(
        "--rubric-version",
        default="",
        help="Rubric version tag to embed in every output row for cross-run traceability",
    )
    parser.add_argument(
        "--run-batch-id",
        default="",
        help="Run batch identifier to embed in every output row",
    )
    return parser.parse_args()


def iter_jsonl(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8-sig") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError("Malformed JSONL input or log; repair the incomplete record before resuming") from exc


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        text = json.dumps(row, ensure_ascii=False)
        if ACTIVE_API_KEY:
            text = text.replace(ACTIVE_API_KEY, "[REDACTED]")
        handle.write(text + "\n")


IDENTITY_FIELDS = (
    "artifact_id",
    "run_batch_id",
    "repo_full_name",
    "base_version",
    "target_version",
    "published_at",
    "release_sequence_in_sample",
)


def request_identity(row: dict, run_batch_id: str) -> dict:
    identity = {field: row.get(field, "") for field in IDENTITY_FIELDS}
    identity["run_batch_id"] = run_batch_id or identity.get("run_batch_id", "")
    return identity


def load_latest_status(
    path: Path, id_field: str, run_batch_id: str
) -> Dict[str, dict]:
    latest: Dict[str, dict] = {}
    for row in iter_jsonl(path):
        if run_batch_id and row.get("run_batch_id") != run_batch_id:
            continue
        sample_id = row.get(id_field)
        if sample_id:
            latest[sample_id] = row
    return latest


def extract_json_object(text: str) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("empty model response")

    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("model response must be a JSON object")
        return parsed
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```json\s*(\{.*\})\s*```", text, flags=re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))

    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        return json.loads(text[first:last + 1])

    raise ValueError("no valid JSON object found in model response")


def build_messages(system_prompt: str, user_prompt: str, schema_text: str) -> List[dict]:
    final_user_prompt = (
        user_prompt
        + "\n\nJSON schema to follow exactly:\n"
        + schema_text
        + "\n\nReturn one JSON object only. No markdown, no extra explanation."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": final_user_prompt},
    ]


def call_chat_completion(
    api_url: str,
    api_key: str,
    model: str,
    messages: List[dict],
    temperature: float,
    timeout: int,
    disable_thinking: bool = False,
    max_tokens: int = 8192,
) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if disable_thinking:
        payload["enable_thinking"] = False
    response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def resolve_schema_text(schema_path_value: str, cache: Dict[str, str]) -> str:
    schema_path = Path(schema_path_value)
    if not schema_path.is_absolute():
        if not schema_path.exists():
            packaged = Path(__file__).resolve().parents[1] / "prompts/schemas" / schema_path.name
            if packaged.exists():
                schema_path = packaged
        schema_path = schema_path.resolve()
    cache_key = str(schema_path)
    if cache_key not in cache:
        cache[cache_key] = schema_path.read_text(encoding="utf-8")
    return cache[cache_key]


def main() -> int:
    args = parse_args()
    global ACTIVE_API_KEY
    api_key = os.environ.get(args.api_key_env)
    ACTIVE_API_KEY = api_key or ""
    if not api_key:
        raise RuntimeError(f"API key not provided. Set the environment variable {args.api_key_env}.")

    requests_path = Path(args.requests_path)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_output_path = output_dir / "raw_responses.jsonl"
    parsed_output_path = output_dir / "parsed_outputs.jsonl"
    status_path = output_dir / "status.jsonl"
    summary_path = output_dir / "run_summary.json"

    request_rows = list(iter_jsonl(requests_path))
    if args.max_samples is not None:
        request_rows = request_rows[: args.max_samples]
    request_ids = [row.get(args.id_field) for row in request_rows]
    if any(not sample_id for sample_id in request_ids):
        raise ValueError(f"Request row missing id field: {args.id_field}")
    if len(request_ids) != len(set(request_ids)):
        raise ValueError(
            f"Duplicate {args.id_field} values in request file; refusing ambiguous output"
        )
    request_batch_ids = {
        str(row.get("run_batch_id") or "").strip()
        for row in request_rows
        if str(row.get("run_batch_id") or "").strip()
    }
    if args.run_batch_id and any(
        batch_id != args.run_batch_id for batch_id in request_batch_ids
    ):
        raise ValueError(
            f"Request metadata batch {sorted(request_batch_ids)} does not match "
            f"--run-batch-id={args.run_batch_id}"
        )

    existing_batches = {
        str(row.get("run_batch_id") or "").strip()
        for row in iter_jsonl(status_path)
        if str(row.get("run_batch_id") or "").strip()
    }
    if existing_batches and (
        not args.run_batch_id or existing_batches != {args.run_batch_id}
    ):
        raise ValueError(
            f"Output directory already contains batch(es) {sorted(existing_batches)}; "
            "use a batch-specific output directory"
        )

    latest_status = (
        load_latest_status(status_path, args.id_field, args.run_batch_id)
        if args.resume
        else {}
    )
    run_summary = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "api_url": args.api_url,
        "model": args.model,
        "rubric_version": args.rubric_version,
        "run_batch_id": args.run_batch_id,
        "api_key_env": args.api_key_env,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "disable_thinking": args.disable_thinking,
        "max_concurrency": args.max_concurrency,
        "request_target": len(request_rows),
        "completed_before_run": sum(1 for row in latest_status.values() if row.get("status") == "completed"),
        "failed_before_run": sum(1 for row in latest_status.values() if row.get("status") == "failed"),
        "completed_in_this_run": 0,
        "failed_in_this_run": 0,
    }

    schema_cache: Dict[str, str] = {}
    for row in request_rows:
        sample_id = row.get(args.id_field)
        schema_path = row.get("schema_path")
        if not schema_path:
            raise ValueError(f"Request row {sample_id} missing schema_path")
        resolve_schema_text(schema_path, schema_cache)

    pending_rows = []
    for index, row in enumerate(request_rows, start=1):
        sample_id = row[args.id_field]
        if args.resume and latest_status.get(sample_id, {}).get("status") == "completed":
            print(f"[{index}/{len(request_rows)}] reused {sample_id}", flush=True)
            continue
        pending_rows.append((index, row))

    write_lock = threading.Lock()
    state_lock = threading.Lock()

    def process_one(index_and_row):
        index, row = index_and_row
        sample_id = row[args.id_field]
        identity = request_identity(row, args.run_batch_id)
        schema_text = resolve_schema_text(row["schema_path"], schema_cache)
        messages = build_messages(row["system_prompt"], row["user_prompt"], schema_text)

        last_error = None
        for attempt in range(1, args.max_retries + 1):
            try:
                result = call_chat_completion(
                    api_url=args.api_url,
                    api_key=api_key,
                    model=args.model,
                    messages=messages,
                    temperature=args.temperature,
                    timeout=args.timeout,
                    disable_thinking=args.disable_thinking,
                    max_tokens=args.max_tokens,
                )
                content = result["choices"][0]["message"]["content"]
                parsed = extract_json_object(content)

                with write_lock:
                    append_jsonl(
                        raw_output_path,
                        {
                            args.id_field: sample_id,
                            **identity,
                            "attempt": attempt,
                            "model": args.model,
                            "rubric_version": args.rubric_version,
                            "run_batch_id": args.run_batch_id,
                            "raw_content": content,
                            "response_json": result,
                        },
                    )
                    append_jsonl(
                        parsed_output_path,
                        {
                            args.id_field: sample_id,
                            **identity,
                            "model": args.model,
                            "model_stage1": row.get("model_stage1", ""),
                            "rubric_version": args.rubric_version,
                            "run_batch_id": args.run_batch_id,
                            "parsed_output": parsed,
                        },
                    )
                    append_jsonl(
                        status_path,
                        {
                            args.id_field: sample_id,
                            **identity,
                            "status": "completed",
                            "attempt": attempt,
                            "rubric_version": args.rubric_version,
                            "run_batch_id": args.run_batch_id,
                            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        },
                    )
                with state_lock:
                    latest_status[sample_id] = {"status": "completed"}
                    run_summary["completed_in_this_run"] += 1
                print(f"[{index}/{len(request_rows)}] completed {sample_id}", flush=True)
                if args.sleep_seconds > 0:
                    time.sleep(args.sleep_seconds)
                return
            except Exception as exc:
                last_error = str(exc).replace(api_key, "[REDACTED]")
                print(f"[{index}/{len(request_rows)}] retry {sample_id} attempt {attempt}: {last_error}", flush=True)
                time.sleep(min(2 ** attempt, 15))

        with write_lock:
            append_jsonl(
                status_path,
                {
                    args.id_field: sample_id,
                    **request_identity(row, args.run_batch_id),
                    "status": "failed",
                    "error": last_error,
                    "rubric_version": args.rubric_version,
                    "run_batch_id": args.run_batch_id,
                    "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                },
            )
        with state_lock:
            latest_status[sample_id] = {"status": "failed", "error": last_error}
            run_summary["failed_in_this_run"] += 1

    max_workers = max(1, int(args.max_concurrency))
    if max_workers == 1:
        for item in pending_rows:
            process_one(item)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_one, item) for item in pending_rows]
            for future in concurrent.futures.as_completed(futures):
                future.result()

    final_status = load_latest_status(status_path, args.id_field, args.run_batch_id)
    run_summary["completed_total"] = sum(1 for row in final_status.values() if row.get("status") == "completed")
    run_summary["failed_total"] = sum(1 for row in final_status.values() if row.get("status") == "failed")
    run_summary["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    summary_path.write_text(json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(run_summary, ensure_ascii=False, indent=2))
    return 1 if run_summary["failed_in_this_run"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
