"""RQ1: per-release macro means; undefined metrics are excluded separately."""
import argparse
import json
from common import COHORT, METRICS, metric_rows, summary


def analyze(rows):
    return [dict(model=model, metric=metric,
                 **summary([r for r in rows if r['model'] == model], metric))
            for model in ('DS', 'QW') for metric in METRICS]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metrics', required=True, help='External final release-metrics CSV (not distributed)')
    parser.add_argument('--cohort', default=COHORT)
    args = parser.parse_args()
    print(json.dumps(analyze(metric_rows(args.metrics, args.cohort)), indent=2, allow_nan=False))
