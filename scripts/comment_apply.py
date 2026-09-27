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
C_LIKE_EXT = {'java', 'kt', 'kts', 'ts', 'tsx', 'js', 'jsx', 'mjs', 'cjs', 'go', 'rs',
              'swift', 'c', 'h', 'cc', 'cpp', 'hpp', 'cs', 'scala', 'dart', 'php',
              'groovy', 'gradle', 'm', 'mm'}
HASH_EXT = {'py', 'sh', 'bash', 'zsh', 'rb', 'yml', 'yaml', 'toml', 'r', 'pl', 'ps1'}
DASH_EXT = {'sql', 'lua', 'hs'}


def comment_kind(path):
    ext = path.rsplit('.', 1)[-1].lower() if '.' in path else ''
    base = path.replace('\\', '/').rsplit('/', 1)[-1]
    if ext in C_LIKE_EXT:
        return 'c'
    if ext in HASH_EXT or base in ('Dockerfile', 'Makefile'):
        return 'hash'
    if ext in DASH_EXT:
        return 'dash'
    return None


def read_utf8(path):
    with open(path, encoding='utf-8', newline='') as fh:
        return fh.read()


def write_utf8(path, text):
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(text)


def split_text(text):
    """본문 줄과 기존 줄바꿈 형식을 반환한다."""
    newline = '\r\n' if '\r\n' in text else '\r' if '\r' in text else '\n'
    normalized = text.replace('\r\n', '\n').replace('\r', '\n')
    return normalized.split('\n'), newline


def require(condition, message):
    if not condition:
        raise ValueError(message)


def render(orig, text):
    first = orig[0]
    m = COMMENT.match(first)
    body = [t.rstrip() for t in text]
    if not m:
        # 코드 줄 끝의 // 주석
        require(len(orig) == 1 and '//' in first, f'주석이 아닌 줄: {first!r}')
        code = first.split('//', 1)[0].rstrip()
        require(len(body) == 1, '줄 끝 주석은 한 줄로만 교체할 수 있음')
        return [f'{code} // {body[0]}']
    indent, marker = m.group(1), m.group(2)
    if marker == '{/*':
        require(len(body) == 1, 'JSX 주석은 한 줄로만 교체할 수 있음')
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
    for line in read_utf8(spec_path).splitlines():
        if line.startswith('@@ '):
            path, rng = line[3:].rsplit(':', 1)
            a, _, b = rng.partition('-')
            cur = (int(a), int(b or a), [])
            edits[path].append(cur)
        elif cur is not None:
            cur[2].append(line)
    updates = []
    for path, items in edits.items():
        lines, newline = split_text(read_utf8(path))
        for a, b, text in sorted(items, key=lambda x: -x[0]):
            while text and not text[-1].strip():
                text.pop()
            orig = lines[a - 1:b]
            for o in orig[:-1] if len(orig) > 1 else []:
                require(COMMENT.match(o), f'{path}:{a}-{b} 주석 아님: {o!r}')
            if len(orig) > 1:
                require(COMMENT.match(orig[-1]), f'{path}:{b} 주석 아님: {orig[-1]!r}')
            lines[a - 1:b] = render(orig, text)
        updates.append((path, newline.join(lines), len(items)))
    # 모든 스펙을 검증한 뒤 기록해 중간 실패 시 일부 파일만 바뀌는 일을 방지한다.
    for path, text, count in updates:
        write_utf8(path, text)
        print(f'{path}: {count}')


def comment_index(line, marker):
    """문자열 밖에서 시작하는 첫 주석 기호 위치."""
    quote = None
    escaped = False
    i = 0
    while i < len(line):
        ch = line[i]
        if escaped:
            escaped = False
        elif ch == '\\' and quote:
            escaped = True
        elif quote:
            if ch == quote:
                quote = None
        elif ch in ('"', "'", '`'):
            quote = ch
        elif line.startswith(marker, i):
            return i
        i += 1
    return -1


def strip_c_comments(line):
    """문자열을 보존하면서 한 줄의 C 계열 주석만 제거한다."""
    out = []
    quote = None
    escaped = False
    i = 0
    while i < len(line):
        ch = line[i]
        if escaped:
            out.append(ch)
            escaped = False
            i += 1
            continue
        if quote:
            out.append(ch)
            if ch == '\\':
                escaped = True
            elif ch == quote:
                quote = None
            i += 1
            continue
        if ch in ('"', "'", '`'):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if line.startswith('//', i):
            break
        if line.startswith('/*', i):
            end = line.find('*/', i + 2)
            if end == -1:
                break
            i = end + 2
            continue
        out.append(ch)
        i += 1
    return ''.join(out).strip()


def code_part(line, path=''):
    """주석을 제외한 코드 부분. 애매한 줄은 코드로 간주해 검증을 실패시킨다."""
    stripped = line.strip()
    ext = path.rsplit('.', 1)[-1].lower() if '.' in path else ''
    kind = comment_kind(path)

    if kind == 'c':
        if stripped.startswith('//'):
            return ''
        if stripped.startswith('/*'):
            end = stripped.find('*/', 2)
            return stripped[end + 2:].strip() if end != -1 else ''
        if stripped.startswith('*/'):
            return stripped[2:].strip()
        if re.match(r'^\*(?:\s|/|$)', stripped):
            return ''
        return strip_c_comments(line)
    elif kind == 'hash':
        if stripped.startswith('#!') or (ext == 'ps1' and re.match(r'#requires\b', stripped, re.I)):
            return stripped
        if stripped.startswith('#'):
            return ''
        markers = ('#',)
    elif kind == 'dash':
        if stripped.startswith('--'):
            return ''
        markers = ('--',)
    else:
        return stripped

    positions = [pos for marker in markers if (pos := comment_index(line, marker)) >= 0]
    return line[:min(positions)].strip() if positions else stripped


def verify(rev=None):
    base = rev or 'HEAD'

    def git_output(args):
        return subprocess.run(['git'] + args, capture_output=True, text=True,
                              encoding='utf-8', check=True).stdout

    # HEAD와 비교해 staged·unstaged 변경을 모두 검사한다. 기본 git diff만 사용하면
    # staged 변경이 누락되어 코드가 바뀌어도 통과할 수 있다.
    diff = git_output(['diff', '-U0', base, '--'])
    unsafe = []
    for line in git_output(['diff', '--numstat', base, '--']).splitlines():
        added_count, removed_count, changed_path = line.split('\t', 2)
        if added_count == removed_count == '-':
            unsafe.append((changed_path, '바이너리 변경은 주석 여부를 검증할 수 없음'))
    for changed_path in git_output(['ls-files', '--others', '--exclude-standard', '-z']).split('\0'):
        if changed_path and comment_kind(changed_path):
            unsafe.append((changed_path, '추적되지 않은 새 파일은 기준 버전이 없어 검증할 수 없음'))
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
            code = code_part(line[1:], path)
            if code:
                removed[code] += 1
        elif line.startswith('+'):
            code = code_part(line[1:], path)
            if code:
                added[code] += 1
    flush()
    for p, gone, new in bad:
        print(f'{p}: 주석 외 줄 변경')
        for c in gone:
            print(f'  - {c}')
        for c in new:
            print(f'  + {c}')
    for p, reason in unsafe:
        print(f'{p}: {reason}')
    count = len(bad) + len(unsafe)
    print('주석 외 변경 없음' if not count else f'확인 필요 파일 {count}개')
    return 1 if count else 0


if __name__ == '__main__':
    if sys.argv[1:2] == ['--verify']:
        sys.exit(verify(sys.argv[2] if len(sys.argv) > 2 else None))
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1])
