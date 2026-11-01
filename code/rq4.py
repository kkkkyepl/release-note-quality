"""RQ4: original 780-record trends, phase differences and Accuracy uncertainty."""
import argparse
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
import json
import math
from pathlib import Path
import numpy as np
import pymannkendall as mk
from common import PACKAGE, read_csv

METRICS = ('accuracy_relaxed', 'recall_relaxed', 'f1_relaxed', 'attribute_completeness_overall')
# Fixed repository order preserves the original bootstrap random-seed allocation.
REPOS = ('electron/electron', 'storybookjs/storybook', 'hashicorp/vault',
         'ggml-org/llama.cpp', 'gravitational/teleport', 'grafana/grafana',
         'jenkinsci/jenkins', 'home-assistant/core', 'Azure/azure-sdk-for-net',
         'BerriAI/litellm', 'kestra-io/kestra', 'dotnet/runtime')


def rounded(value, digits):
    return float(Decimal(str(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def indices(n, repetitions, length, rng):
    starts = rng.integers(0, n, size=(repetitions, math.ceil(n/length)))
    return ((starts[..., None]+np.arange(length)) % n).reshape(repetitions, -1)[:, :n]


def analyze(rows, repetitions=10000, seed=20261023):
    rows = [r for r in rows if r['evaluation_status'] == 'completed']
    groups = defaultdict(list)
    for row in rows:
        groups[row['repo_full_name']].append(row)
    if len(rows) != 780 or set(groups) != set(REPOS):
        raise ValueError('Expected the original 780 records across 12 repositories')
    results = []
    for repo_index, repo in enumerate(REPOS):
        group = sorted(groups[repo], key=lambda r: int(r['release_sequence_in_repo']))
        if [int(r['release_sequence_in_repo']) for r in group] != list(range(1, len(group)+1)):
            raise ValueError('Invalid original release sequence')
        cutoff = len(group)//3
        for metric in METRICS:
            values = np.array([float(r[metric]) for r in group])
            if not np.isfinite(values).all() or ((values<0)|(values>1)).any():
                raise ValueError('Invalid longitudinal metric values')
            test = mk.original_test(values)
            early, late = values[:cutoff], values[-cutoff:]
            delta = float(late.mean()-early.mean())
            stars = '***' if test.p < .001 else '**' if test.p < .01 else '*' if test.p < .05 else ''
            result = dict(repo=repo, metric=metric, n=len(group), n_phase=cutoff,
                tau=float(test.Tau), p=float(test.p), stars=stars,
                early_mean=float(early.mean()), late_mean=float(late.mean()), delta=delta,
                # Original reporting rounded source summaries to four decimals first.
                reported_tau=rounded(rounded(test.Tau,4),3), reported_delta=rounded(rounded(delta,4),2))
            if metric == 'accuracy_relaxed':
                for length in (2,3,4):
                    rng = np.random.default_rng(seed+repo_index*1009+length*17)
                    e = indices(len(early),repetitions,length,rng)
                    l = indices(len(late),repetitions,length,rng)
                    draws = late[l].mean(axis=1)-early[e].mean(axis=1)
                    result[f'ci_L{length}'] = np.quantile(draws,[.025,.975]).tolist()
            results.append(result)
    return results


def annual(rows):
    # The original supplied metrics table has no usable dates. Optional dated
    # records must preserve the original observations and metric values.
    groups = defaultdict(list)
    for row in rows:
        value = row.get('audit_published_at') or row.get('published_at', '')
        if not value:
            raise ValueError('Annual analysis requires verified publication dates for every record')
        year = int(value[:4])
        if year in (2024,2025):
            groups[row['repo_full_name'],year].append(row)
    selected = [r for r in REPOS if (r,2024) in groups and (r,2025) in groups]
    keys = ('accuracy_relaxed','recall_relaxed','attribute_completeness_overall')
    output = []
    for repo in selected:
        item = {'repo':repo}
        for year in (2024,2025):
            item[str(year)] = {m:float(np.mean([float(r[m]) for r in groups[repo,year]])) for m in keys}
        output.append(item)
    return {'repositories':output,'equal_repository_means':
        {str(y):{m:float(np.mean([r[str(y)][m] for r in output])) for m in keys} for y in (2024,2025)}}


def categories(results):
    output = {}
    for repo in REPOS:
        group = [r for r in results if r['repo'] == repo]
        positive = sum(r['tau'] > 0 and r['p'] < .05 for r in group)
        negative = any(r['tau'] < 0 and r['p'] < .05 for r in group)
        output[repo] = ('decline' if negative else 'joint_improvement' if positive == 4
                        else 'selective_improvement' if positive else 'unresolved')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=PACKAGE/'data/used/longitudinal_metrics.csv')
    parser.add_argument('--bootstrap-reps', type=int, default=10000)
    parser.add_argument('--seed', type=int, default=20261023)
    args = parser.parse_args()
    if args.bootstrap_reps < 100:
        parser.error('Use at least 100 bootstrap resamples')
    rows = read_csv(args.data)
    result = {'trends':analyze(rows,args.bootstrap_reps,args.seed)}
    result['categories'] = categories(result['trends'])
    result['annual'] = annual(rows) if all(r.get('audit_published_at') or r.get('published_at') for r in rows) else {'status':'not_available: original table lacks publication dates'}
    print(json.dumps(result,indent=2,allow_nan=False))
