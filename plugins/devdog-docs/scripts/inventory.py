#!/usr/bin/env python3
"""Draft a migration plan for existing Markdown files.

The plan is a starting point. Titles and bodies decide the final class;
review every entry before running apply_moves.py.
"""
import argparse
import json
import re
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / 'templates' / 'tools'))
from check_docs import load_config, relative, title  # noqa: E402

FIXED_ROOT = {'readme.md', 'agents.md', 'claude.md', 'changelog.md', 'contributing.md', 'security.md',
              'code_of_conduct.md', 'license.md', 'gemini.md', 'copilot-instructions.md'}
SKIP_DIRS = {'.git', 'node_modules', 'dist', 'build', 'out', 'target', 'vendor', '.venv', 'venv',
             '__pycache__', '.next', '.expo', 'coverage', '.site', '.vitepress'}
RULES = [
    # (kind, audience, English tokens, Korean tokens and patterns, reason)
    ('ai', 'ai', ['prompt', 'prompts', 'agent', 'agents', 'claude', 'copilot', 'cursor', 'cursorrules', 'llm',
                  'ai-guide', 'ai-rules', 'ai-instructions'],
     ['프롬프트'], 'AI 지시·프롬프트 문서로 보이는 이름'),
    ('archive', 'human', ['archive', 'legacy', 'deprecated', 'old', 'draft', 'report', 'retro', 'retrospective'],
     ['회의', '회고', '보고서', '초안', r'\d{4}-\d{2}-\d{2}', r'(?<!\d)\d{8}(?!\d)'],
     '과거 기록·초안·날짜가 있는 보고서로 보이는 이름'),
    ('tutorials', 'human', ['tutorial', 'tutorials', 'getting-started', 'quickstart', 'quick-start', 'first-day',
                            'onboarding'],
     ['시작하기', '입문', '온보딩'], '처음 따라 하는 안내로 보이는 이름'),
    ('how-to', 'human', ['how-to', 'howto', 'guide', 'deploy', 'deployment', 'setup', 'install', 'installation',
                         'release', 'runbook', 'operations', 'migration', 'troubleshooting'],
     ['배포', '설치', '운영', '절차', '가이드', '릴리스'], '작업 절차 문서로 보이는 이름'),
    ('reference', 'human', ['api', 'reference', 'spec', 'specification', 'convention', 'conventions', 'schema',
                            'config', 'configuration', 'enum', 'errors', 'glossary', 'style'],
     ['규칙', '명세', '용어', '컨벤션', '설정'], '규칙·값을 찾는 참조 문서로 보이는 이름'),
]


def pattern(english, korean):
    """English tokens match between non-letters: 'old' matches OLD_API.md, not folder.md."""
    words = [r'(?<![a-z])%s(?![a-z])' % re.escape(w).replace(r'\-', '[-_ ]?') for w in english]
    return re.compile('|'.join(words + korean), re.I)


RULE_PATTERNS = [(kind, audience, pattern(en, ko), reason) for kind, audience, en, ko, reason in RULES]


def kebab(stem):
    text = re.sub(r'([a-z0-9])([A-Z])', r'\1-\2', stem)
    text = re.sub(r'[\s_]+', '-', text).lower()
    text = re.sub(r'-+', '-', text).strip('-')
    return text or 'document'


def classify(rel, heading):
    haystack = '%s %s' % (rel, heading)
    for kind, audience, compiled, reason in RULE_PATTERNS:
        if compiled.search(haystack):
            return kind, audience, reason
    return 'explanation', 'human', '해당 규칙 없음. 구조·배경 설명으로 분류'


def candidates(root, keep_dirs):
    for path in sorted(root.rglob('*.md')):
        rel = relative(path, root)
        parts = rel.parts
        if any(p in SKIP_DIRS or (p.startswith('.') and p != '.github') for p in parts[:-1]):
            continue
        yield path, rel.as_posix(), keep_dirs


def build_plan(config, repo_id):
    repo = config['repos'][repo_id]
    root = repo['root']
    moves, keep, used = [], [], set()
    managed = [repo['human'], repo['ai']]
    for path, rel, _ in candidates(root, managed):
        name = path.name.lower()
        if any(rel == d or rel.startswith(d.rstrip('/') + '/') for d in managed):
            continue
        if '/' not in rel and name in FIXED_ROOT:
            keep.append({'path': rel, 'reason': '저장소 루트 위치 고정 파일'})
            continue
        if name == 'readme.md' and not rel.startswith('docs/'):
            keep.append({'path': rel, 'reason': '코드 폴더 옆 README. 관련 파일과 같은 위치 유지'})
            continue
        if rel.startswith('.github/'):
            keep.append({'path': rel, 'reason': 'GitHub 설정 문서'})
            continue
        heading = title(path)
        kind, audience, reason = classify(rel, heading)
        stem = path.parent.name if name == 'readme.md' else path.stem
        base = kebab(stem)
        folder = repo['ai'] if audience == 'ai' else '%s/%s' % (repo['human'], kind)
        target = '%s/%s.md' % (folder, base)
        n = 2
        while target in used or ((root / target).exists() and target != rel):
            target = '%s/%s-%d.md' % (folder, base, n); n += 1
        used.add(target)
        moves.append({'from': rel, 'to': target, 'audience': audience, 'kind': kind if audience == 'human' else 'ai',
                      'title': heading, 'reason': reason})
    return {'schema_version': 1, 'repository': repo_id, 'moves': moves, 'keep': keep}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--root', default='.', help='Repository that owns docs.config.json.')
    parser.add_argument('--config')
    parser.add_argument('--repository', help='Repository id. Default: the home repository.')
    parser.add_argument('--output', help='Plan file. Default: <repository>/docs-migration-plan.json')
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    config = load_config(root, Path(args.config).resolve() if args.config else root / 'docs.config.json')
    repo_id = args.repository or config['home']
    plan = build_plan(config, repo_id)
    output = Path(args.output) if args.output else config['repos'][repo_id]['root'] / 'docs-migration-plan.json'
    output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for move in plan['moves']:
        print('%-10s %s -> %s' % (move['kind'], move['from'], move['to']))
    for item in plan['keep']:
        print('%-10s %s (%s)' % ('keep', item['path'], item['reason']))
    print('Planned %d moves, %d kept files. Review %s before applying.' % (len(plan['moves']), len(plan['keep']), output))
    return 0


if __name__ == '__main__':
    # Windows 콘솔 기본 인코딩(cp1252 등)에서 한글 경로·문구 출력 시 UnicodeEncodeError 방지
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.exit(main())
