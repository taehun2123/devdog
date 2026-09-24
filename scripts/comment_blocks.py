#!/usr/bin/env python3
"""kolint 위반이 있는 코드 주석 블록을 줄 번호와 함께 출력한다.

출력은 comment_apply.py 스펙을 작성하는 입력으로 사용한다.
사용법: comment_blocks.py PATH...
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kolint  # noqa: E402

MARK = {'c': re.compile(r'^\s*(///|//|/\*|\*|\{/\*)'), 'hash': re.compile(r'^\s*#'), 'dash': re.compile(r'^\s*--')}


def blocks(path, cfg):
    kind = kolint.kind_of(path)
    if kind not in MARK or kolint.is_excluded(cfg, path):
        return []
    findings = kolint.lint_file(path, cfg)
    if not findings:
        return []
    by_line = {}
    for f in findings:
        by_line.setdefault(f.line, []).append(f)
    with open(path, encoding='utf-8') as fh:
        lines = fh.read().split('\n')
    out, i = [], 0
    while i < len(lines):
        if MARK[kind].match(lines[i]):
            j = i
            while j + 1 < len(lines) and MARK[kind].match(lines[j + 1]):
                j += 1
        elif i + 1 in by_line:
            j = i                      # 코드 뒤에 붙은 주석
        else:
            i += 1
            continue
        hits = [f for n in range(i + 1, j + 2) for f in by_line.get(n, [])]
        if hits:
            out.append((i + 1, j + 1, lines[i:j + 1], hits))
        i = j + 1
    return out


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cfg = kolint.load_config(argv[0])
    total = 0
    for path in kolint.iter_files(argv):
        found = blocks(path, cfg)
        if not found:
            continue
        print(f'=== {path}')
        for n, (a, b, body, hits) in enumerate(found):
            if n:
                print('--')
            for k, line in enumerate(body, a):
                print(f'{k}: {line}')
            for f in hits:
                print(f'  ! {f.line} [{f.rule}] {f.detail}'.rstrip())
            total += 1
    print(f'# 블록 {total}개', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
