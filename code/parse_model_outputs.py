"""Reparse archived raw responses locally; no model calls or credentials needed."""
import argparse
import json
from pathlib import Path
from run_llm import extract_json_object, iter_jsonl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.raw.resolve() == args.output.resolve() or args.output.exists():
        raise FileExistsError('Choose a new output file; input/output overwriting is disabled')
    if not args.raw.is_file():
        raise FileNotFoundError('Raw-response input does not exist')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    failed = completed = 0
    # Keep row metadata and order. Repeated attempts are not silently deduplicated.
    with args.output.open('x', encoding='utf-8') as out:
        for row in iter_jsonl(args.raw):
            try:
                content = row.get('raw_content')
                if content is None:
                    content = row['response_json']['choices'][0]['message']['content']
                parsed = extract_json_object(content)
            except (ValueError, KeyError, IndexError, TypeError):
                failed += 1
                continue
            result = {k: v for k, v in row.items() if k not in ('raw_content', 'response_json', 'parsed_output')}
            result['parsed_output'] = parsed
            out.write(json.dumps(result, ensure_ascii=False)+'\n')
            completed += 1
    print(json.dumps({'parsed': completed, 'failed': failed}))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
