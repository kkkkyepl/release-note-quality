"""RQ3: pooled release-relevant facts and omission risk against all other types."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from common import COHORT, cohort

TYPES = ('api_change', 'configuration', 'deprecation', 'feature', 'dependency',
         'refactor', 'behavior_change', 'performance', 'docs_only', 'bugfix',
         'build_ci', 'security', 'test_only', 'other')
LABELS = ('covered', 'partially_covered', 'not_covered')


def facts_from_file(path, ids):
    seen, facts = set(), []
    with Path(path).open(encoding='utf-8-sig') as handle:
        for line in handle:
            if not line.strip():
                continue
            wrapper = json.loads(line)
            payload = wrapper.get('parsed_output', wrapper)
            sid = payload.get('sample_id', wrapper.get('sample_id'))
            if sid not in ids:
                continue
            if sid in seen:
                raise ValueError('Duplicate sample ID; provide a single final snapshot per release')
            seen.add(sid)
            for fact in payload.get('fact_alignments', []):
                relevant = fact.get('should_appear_in_release_notes')
                if relevant is None and fact.get('should_appear_inlease_notes') is False:
                    relevant = False
                if not isinstance(relevant, bool):
                    raise ValueError('Missing or non-boolean relevance label')
                if relevant:
                    facts.append(fact)
    if seen != set(ids):
        raise ValueError('Judgments do not cover the complete final cohort')
    return facts


def analyze(facts):
    groups = defaultdict(Counter)
    for fact in facts:
        label = fact['coverage_label']
        if label not in LABELS:
            raise ValueError('Nonstandard coverage label; use final corrected judgments')
        kind = fact.get('change_type', 'other').strip()
        kind = kind if kind in TYPES else 'other'
        required = {str(x).strip() for x in fact.get('required_attributes', []) if str(x).strip()}
        covered = {str(x).strip() for x in fact.get('covered_attributes', []) if str(x).strip()}
        g = groups[kind]
        g['n_facts'] += 1
        g[label] += 1
        g['required_attributes'] += len(required)
        g['covered_required_attributes'] += len(required & covered)
    total = sum(g['n_facts'] for g in groups.values())
    omitted = sum(g['not_covered'] for g in groups.values())
    output = []
    for kind in TYPES:
        g = groups[kind]
        n = g['n_facts']
        if not n:
            continue
        risk = g['not_covered']/n
        other_n, other_omitted = total-n, omitted-g['not_covered']
        baseline = other_omitted/other_n if other_n else None
        output.append(dict(change_type=kind, n_facts=n,
            covered=g['covered'], partially_covered=g['partially_covered'], not_covered=g['not_covered'],
            strict_recall=g['covered']/n, relaxed_recall=(g['covered']+.5*g['partially_covered'])/n,
            attribute_completeness=g['covered_required_attributes']/g['required_attributes'] if g['required_attributes'] else None,
            not_covered_rate=risk, omission_risk_ratio=risk/baseline if baseline else None))
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--judgments', required=True, help='External final judgments JSONL for one model (not distributed)')
    parser.add_argument('--model', required=True, choices=['DS', 'QW'])
    parser.add_argument('--cohort', default=COHORT)
    args = parser.parse_args()
    result = analyze(facts_from_file(args.judgments, cohort(args.cohort)))
    print(json.dumps({'model': args.model, 'results': result}, indent=2, allow_nan=False))
