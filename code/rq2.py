"""RQ2: descriptive stratification by release size, language, owner and maturity."""
import argparse
import json
from common import COHORT, GROUPS, metric_rows, summary

REPORTED = ('accuracy_relaxed', 'recall_relaxed', 'f1_relaxed',
            'attribute_completeness_overall', 'hallucination_rate',
            'breaking_change_omission_rate')


def analyze(rows):
    results = []
    for model in ('DS', 'QW'):
        for dimension, strata in GROUPS.items():
            for stratum in strata:
                group = [r for r in rows if r['model'] == model and r[dimension] == stratum]
                for metric in REPORTED:
                    results.append(dict(model=model, dimension=dimension, stratum=stratum,
                                        metric=metric, **summary(group, metric)))
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metrics', required=True, help='External final release-metrics CSV (not distributed)')
    parser.add_argument('--cohort', default=COHORT)
    args = parser.parse_args()
    print(json.dumps(analyze(metric_rows(args.metrics, args.cohort)), indent=2, allow_nan=False))
