#!/usr/bin/env python3
"""플러그인 있음·없음 비교 실험.

같은 작성 요청을 두 조건으로 실행하고, 생성된 파일을 kolint로 검사한다.
사용자 전역 설정(~/.claude/CLAUDE.md, 설치 플러그인)은 --setting-sources project,local로 제외한다.

사용법: python3 evals/ablation.py [--runs N] [--model MODEL] [--jobs N]
결과: evals/results/ablation-<시각>.json 과 요약 표 출력
"""
import argparse
import concurrent.futures
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import kolint  # noqa: E402

CASES = json.load(open(os.path.join(os.path.dirname(__file__), 'cases.json'), encoding='utf-8'))


def score(case, text):
    cfg = kolint.load_config('/nonexistent')
    if not text:
        findings = []
    elif case['kind'] == 'commit':
        findings = kolint.lint_commit(text, cfg)
    else:
        findings = kolint.lint_text(text, case['file'], cfg)
    return {'errors': sum(f.sev == 'error' for f in findings), 'warns': sum(f.sev == 'warn' for f in findings),
            'rules': sorted({f.rule for f in findings}),
            'missing_facts': [f for f in case['facts'] if not re.search(f, text)]}


def run_case(case, arm, model, idx):
    work = tempfile.mkdtemp(prefix=f'kt-{case["id"]}-{arm}-')
    subprocess.run(['git', 'init', '-q'], cwd=work, check=True)
    cmd = ['claude', '-p', '--setting-sources', 'project,local', '--model', model,
           '--permission-mode', 'acceptEdits', '--allowedTools', 'Write,Edit,Read,Skill',
           '--output-format', 'json']
    if arm == 'with':
        cmd += ['--plugin-dir', ROOT]
    proc = subprocess.run(cmd, input=case['prompt'], cwd=work, capture_output=True, text=True, timeout=600)
    try:
        meta = json.loads(proc.stdout)
    except json.JSONDecodeError:
        meta = {}
    path = os.path.join(work, case['file'])
    text = open(path, encoding='utf-8').read() if os.path.isfile(path) else ''
    return {
        'case': case['id'], 'arm': arm, 'run': idx, 'dir': work, 'exists': bool(text),
        **score(case, text),
        'cost_usd': meta.get('total_cost_usd'), 'text': text,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', type=int, default=2)
    ap.add_argument('--model', default='sonnet')
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--rescore', help='저장된 결과 JSON을 현재 kolint로 다시 채점')
    args = ap.parse_args()
    if args.rescore:
        with open(args.rescore, encoding='utf-8') as f:
            saved = json.load(f)
        by_id = {c['id']: c for c in CASES}
        results = [{**r, **score(by_id[r['case']], r['text'])} for r in saved['results']]
        args.model, args.runs = saved['model'], saved['runs']
        report(results)
        return
    jobs = [(c, arm, i) for c in CASES for arm in ('without', 'with') for i in range(args.runs)]
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as ex:
        results = list(ex.map(lambda j: run_case(j[0], j[1], args.model, j[2]), jobs))
    os.makedirs(os.path.join(ROOT, 'evals', 'results'), exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    out = os.path.join(ROOT, 'evals', 'results', f'ablation-{stamp}.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'model': args.model, 'runs': args.runs, 'results': results}, f, ensure_ascii=False, indent=2)
    report(results)
    print(out)


def report(results):
    print(f'| 케이스 | 조건 | error | warn | 누락 사실 | 파일 생성 |')
    print('|---|---|---|---|---|---|')
    for c in CASES:
        for arm in ('without', 'with'):
            rs = [r for r in results if r['case'] == c['id'] and r['arm'] == arm]
            print(f"| {c['id']} | {arm} | {sum(r['errors'] for r in rs)} | {sum(r['warns'] for r in rs)} | "
                  f"{sum(len(r['missing_facts']) for r in rs)} | {sum(r['exists'] for r in rs)}/{len(rs)} |")
    for arm in ('without', 'with'):
        rs = [r for r in results if r['arm'] == arm]
        cost = sum(r['cost_usd'] or 0 for r in rs)
        print(f"{arm}: error={sum(r['errors'] for r in rs)} warn={sum(r['warns'] for r in rs)} "
              f"missing_facts={sum(len(r['missing_facts']) for r in rs)} cost=${cost:.2f}")


if __name__ == '__main__':
    main()
