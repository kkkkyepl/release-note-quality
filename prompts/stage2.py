from typing import List

def build_system_prompt() -> str:
    return (
        "You are a software engineering researcher evaluating GitHub release note quality. "
        "Your task: decompose the release note into atomic claims, then judge each claim "
        "against the provided reference change points extracted from the actual code diff. "
        "Do NOT invent code evidence not present in the reference. Return only valid JSON.\n\n"
        "## Claim decomposition rules\n"
        "- Each atomic claim must describe exactly one code change, behavior change, or factual statement.\n"
        "- Separate compound sentences into individual claims.\n"
        "- Preserve the original wording as much as possible.\n\n"
        "## support_label definitions (apply exactly one per claim)\n"
        "- supported: The claim accurately describes a change that is confirmed by one or more reference change points.\n"
        "- partially_supported: The claim is directionally correct but contains details (numbers, scope, mechanism) "
        "that are only partially confirmed or slightly inaccurate relative to the reference.\n"
        "- unsupported: The claim describes a specific code change, feature, or fix, but no matching evidence "
        "exists in the provided reference change points. This means the LLM extractor may have missed it, "
        "or the claim is hallucinated — do NOT assume hallucination; default to unsupported.\n"
        "- contradicted: The claim directly contradicts the reference change points "
        "(e.g., states a feature was added when the reference shows it was removed).\n"
        "- too_vague: The claim is so generic that it cannot be verified even in principle, "
        "even if code evidence existed. Criteria: no module name, no behavior description, "
        "no version number, no affected component — a reader unfamiliar with the project "
        "cannot determine what specifically changed. "
        "Examples: 'Various bug fixes', 'Performance improvements', 'Minor updates'.\n"
        "- non_change: The text is NOT describing a code change at all. Use this label for: "
        "project descriptions ('X is a cross-platform tool that...'), "
        "version number announcements ('This is version 1.2.3'), "
        "installation/download instructions ('Run pip install...'), "
        "SHA/checksum listings, contributor acknowledgments ('Thanks to @user'), "
        "support policy statements ('This is an LTS release'), "
        "prerequisite notices that describe external dependency versions rather than changes in THIS release, "
        "and any other boilerplate that does not describe what changed in this specific release. "
        "non_change claims are excluded from accuracy and hallucination metrics.\n\n"
        "## too_vague vs unsupported distinction\n"
        "If the claim names a specific component, API, module, or behavior (even without code evidence), "
        "use unsupported — not too_vague. "
        "too_vague is reserved for claims that lack ANY verifiable specificity.\n\n"
        "## unsupported vs non_change distinction\n"
        "If the claim is attempting to describe a code change but lacks evidence, use unsupported. "
        "If the text is not attempting to describe a code change at all, use non_change."
    )

def build_reference_block(change_points: List[dict]) -> str:
    lines: List[str] = []
    for point in change_points:
        lines.append(
            f"- fact_id: {point.get('point_id', '')}\n"
            f"  change_type: {point.get('change_type', 'other')}\n"
            f"  importance: {point.get('importance', 'medium')}\n"
            f"  should_appear_in_release_notes: {str(bool(point.get('should_appear_in_release_notes'))).lower()}\n"
            f"  required_attributes: [{', '.join(point.get('required_attributes') or [])}]\n"
            f"  summary: {(point.get('summary') or '').strip()}\n"
            f"  impact: {(point.get('impact') or '').strip()}"
        )
    return "\n\n".join(lines) if lines else "- none"

def build_user_prompt(packet: dict, extraction: dict) -> str:
    repo_meta = packet["repo_metadata"]
    release_meta = packet["release_metadata"]
    release_text = packet["release_text"]
    change_points = extraction.get("reference_change_points") or []

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
        f"Reference change points (extracted from the code diff between base and target version):\n"
        f"{build_reference_block(change_points)}\n\n"
        "Output instructions:\n"
        "1. note_claims: decompose the release note body into atomic claims and assign a support_label to each.\n"
        "   - If a sentence or bullet is non-change content (project description, version announcement, "
        "installation instructions, checksums, acknowledgments, policy statements), label it non_change.\n"
        "   - If a claim names a specific feature/fix/module but has no matching reference change point, "
        "label it unsupported (not non_change and not too_vague).\n"
        "   - Only use too_vague if the claim has zero verifiable specificity.\n"
        "2. fact_alignments: for each reference change point, judge whether and how well it is covered "
        "by the release note claims, and which required attributes are mentioned.\n"
        "3. note_judgment.understandability_score: rate the overall release note understandability 1-5 "
        "(1=incomprehensible, 5=perfectly clear to a developer unfamiliar with the repo).\n"
        "4. Include claim_notes for every claim explaining your reasoning, especially for "
        "non_change, unsupported, and too_vague labels."
    )
