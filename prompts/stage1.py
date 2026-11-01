from typing import List

def build_system_prompt() -> str:
    return (
        "You are helping with a GitHub release-note study. "
        "Given compare evidence between a base version and a target version, "
        "extract evidence-grounded code-change key points. "
        "Use only the supplied evidence and do not infer unsupported changes from the release note. "
        "Return valid JSON only."
    )

def build_user_prompt(packet: dict, evidence: dict) -> str:
    repo_meta = packet["repo_metadata"]
    release_meta = packet["release_metadata"]
    release_text = packet["release_text"]

    commit_lines = [
        f"- {item['sha_short']}: {item['message_first_line']}"
        for item in evidence.get("commit_summaries") or []
    ]

    file_lines = []
    for item in evidence.get("changed_files") or []:
        patch_text = f"\nPATCH:\n{item['patch_excerpt']}" if item.get("patch_excerpt") else ""
        file_lines.append(
            f"- FILE: {item['filename']}\n"
            f"  STATUS: {item['status']}\n"
            f"  ADDITIONS: {item['additions']}\n"
            f"  DELETIONS: {item['deletions']}\n"
            f"  CHANGES: {item['changes']}{patch_text}"
        )

    return (
        f"Sample ID: {packet['sample_id']}\n"
        f"Repository: {repo_meta['repo_full_name']}\n"
        f"Language: {repo_meta['requested_language_name']}\n"
        f"Owner class: {repo_meta['owner_class_initial']}\n"
        f"Maturity: {repo_meta['maturity_label_initial']}\n"
        f"Release size: {release_meta.get('release_size_label', 'unknown')}\n"
        f"Base version: {release_meta['base_version']}\n"
        f"Target version: {release_meta['target_version']}\n\n"
        f"Release note title:\n{release_text.get('name', '')}\n\n"
        f"Release note body:\n{release_text.get('body', '')}\n\n"
        f"Compare summary:\n"
        f"- total_commits: {evidence.get('compare_total_commits')}\n"
        f"- files_returned: {evidence.get('changed_file_count_returned')}\n"
        f"- additions_sum: {evidence.get('compare_additions_sum')}\n"
        f"- deletions_sum: {evidence.get('compare_deletions_sum')}\n"
        f"- status: {evidence.get('compare_status')}\n\n"
        f"Commit summaries:\n" + ("\n".join(commit_lines) if commit_lines else "- none") + "\n\n"
        f"Changed file evidence:\n" + ("\n\n".join(file_lines) if file_lines else "- none") + "\n\n"
        "Extract code-change key points only. Do not judge the release note quality yet."
    )
