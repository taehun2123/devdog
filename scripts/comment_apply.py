#!/usr/bin/env python3
"""주석 블록 교체 도구.

스펙 형식:
    @@ 경로:시작-끝
    새 주석 본문(여러 줄, 빈 줄은 문단 구분)
시작~끝 줄은 모두 주석이어야 한다. 원래 주석 형식과 들여쓰기를 유지해 본문만 바꾼다.
끝 줄이 코드 뒤에 붙은 // 주석이면 // 뒤만 바꾼다. 여러 스펙은 한 파일로 합쳐 한 번에 적용한다.

사용법:
  comment_apply.py SPEC_FILE          스펙 적용 (파일 아래쪽 블록부터 교체)
  comment_apply.py --verify [REV]     git 디프에서 주석 외 코드 줄 변경 여부 검사 (기본: 작업 트리)
"""
import re
import subprocess
import sys
from collections import Counter, defaultdict

COMMENT = re.compile(r'^(\s*)(///|//|/\*\*|/\*|\*|\{/\*|#|--)')


def render(orig, text):
    first = orig[0]
    m = COMMENT.match(first)
    body = [t.rstrip() for t in text]
    if not m:
        # 코드 줄 끝의 // 주석
        assert len(orig) == 1 and '//' in first, f'주석이 아닌 줄: {first!r}'
        code = first.split('//', 1)[0].rstrip()
        assert len(body) == 1
        return [f'{code} // {body[0]}']
    indent, marker = m.group(1), m.group(2)
    if marker == '{/*':
        assert len(body) == 1
        return [f'{indent}{{/* {body[0]} */}}']
    if marker in ('//', '///', '#', '--'):
        return [f'{indent}{marker} {t}' if t else f'{indent}{marker}' for t in body]
    if marker in ('/**', '/*'):
        if len(orig) == 1 and len(body) == 1:
            return [f'{indent}{marker} {body[0]} */']
        out = [f'{indent}{marker}']
        out += [f'{indent} * {t}' if t else f'{indent} *' for t in body]
        out.append(f'{indent} */')
        return out
    raise AssertionError(f'블록 시작이 아님: {first!r}')


def main(spec_path):
    edits = defaultdict(list)
    cur = None
    for line in open(spec_path).read().split('\n'):
        if line.startswith('@@ '):
            path, rng = line[3:].rsplit(':', 1)
            a, _, b = rng.partition('-')
            cur = (int(a), int(b or a), [])
            edits[path].append(cur)
        elif cur is not None:
            cur[2].append(line)
    for path, items in edits.items():
        lines = open(path).read().split('\n')
        for a, b, text in sorted(items, key=lambda x: -x[0]):
            while text and not text[-1].strip():
                text.pop()
            orig = lines[a - 1:b]
            for o in orig[:-1] if len(orig) > 1 else []:
                assert COMMENT.match(o), f'{path}:{a}-{b} 주석 아님: {o!r}'
            if len(orig) > 1:
                assert COMMENT.match(orig[-1]), f'{path}:{b} 주석 아님: {orig[-1]!r}'
            lines[a - 1:b] = render(orig, text)
        open(path, 'w').write('\n'.join(lines))
        print(f'{path}: {len(items)}')


def code_part(line):
    """주석을 제외한 코드 부분. 주석만 있는 줄은 빈 문자열."""
    if COMMENT.match(line) or line.strip().startswith(('*/', '{/*')):
        return ''
    for mark in ('//', ' #', '--'):
        if mark in line:
            line = line.split(mark, 1)[0]
    return line.strip()


def verify(rev=None):
    diff = subprocess.run(['git', 'diff', '-U0'] + ([rev] if rev else []),
                          capture_output=True, text=True, check=True).stdout
    bad, path = [], None
    removed, added = Counter(), Counter()

    def flush():
        if path and removed != added:
            bad.append((path, removed - added, added - removed))
    for line in diff.split('\n'):
        if line.startswith('+++ '):
            flush()
            path, removed, added = line[6:], Counter(), Counter()
        elif line.startswith('-') and not line.startswith('---'):
            code = code_part(line[1:])
            if code:
                removed[code] += 1
        elif line.startswith('+'):
            code = code_part(line[1:])
            if code:
                added[code] += 1
    flush()
    for p, gone, new in bad:
        print(f'{p}: 주석 외 줄 변경')
        for c in gone:
            print(f'  - {c}')
        for c in new:
            print(f'  + {c}')
    print('주석 외 변경 없음' if not bad else f'확인 필요 파일 {len(bad)}개')
    return 1 if bad else 0


if __name__ == '__main__':
    if sys.argv[1:2] == ['--verify']:
        sys.exit(verify(sys.argv[2] if len(sys.argv) > 2 else None))
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1])
