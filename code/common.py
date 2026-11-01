"""Shared input checks for the current paper's RQ1--RQ3 analyses."""
import csv
import math
from pathlib import Path
from statistics import fmean

PACKAGE = Path(__file__).resolve().parents[1]
COHORT = PACKAGE / 'data/used/main_cohort.csv'
METRICS = ('accuracy_strict', 'accuracy_relaxed', 'precision_strict',
           'precision_relaxed', 'recall_strict', 'recall_relaxed',
           'f1_strict', 'f1_relaxed', 'attribute_completeness_overall',
           'hallucination_rate', 'breaking_change_omission_rate')
GROUPS = {
    'release_size_label': ('small', 'medium', 'large'),
    'requested_language_name': ('C#', 'C++', 'Go', 'Java', 'Python', 'TypeScript'),
    'owner_class_initial': ('indie_small_team', 'small_company_startup', 'mid_size_company', 'large_company'),
    'maturity_label_initial': ('emerging', 'growing_stabilizing', 'mature'),
}


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def cohort(path=COHORT):
    rows = read_csv(path)
    index = {r['sample_id']: r for r in rows}
    if len(index) != len(rows) or len(index) != 1418:
        raise ValueError('Expected 1,418 unique final-cohort sample IDs')
    if len({r['repo_full_name'] for r in rows}) != 154:
        raise ValueError('Expected 154 main-study repositories')
    return index


def metric_rows(path, cohort_path=COHORT):
    index = cohort(cohort_path)
    result, seen = [], set()
    for row in read_csv(path):
        sid = row['sample_id']
        if sid not in index:
            continue
        key = row['model'], sid
        if row['model'] not in ('DS', 'QW') or key in seen:
            raise ValueError('Unknown model or duplicate model/sample ID')
        seen.add(key)
        for field in ('repo_full_name', *GROUPS):
            row[field] = index[sid][field]
        for metric in METRICS:
            text = row[metric].strip()
            value = None if text.lower() in ('', 'nan', 'none', 'null') else float(text)
            if value is not None and (not math.isfinite(value) or not 0 <= value <= 1):
                raise ValueError(f'Invalid metric: {metric}')
            row[metric] = value
        result.append(row)
    if seen != {(model, sid) for model in ('DS', 'QW') for sid in index}:
        raise ValueError('Input must contain both models on all 1,418 releases')
    return result


def summary(rows, metric):
    values = [r[metric] for r in rows if r[metric] is not None]
    return {'n_total': len(rows), 'n_valid': len(values),
            'n_undefined': len(rows)-len(values),
            'mean': fmean(values) if values else None}
