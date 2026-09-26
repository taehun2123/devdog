#!/usr/bin/env python3
"""해라체 문장 끝(~한다/~이다/~있다)을 합쇼체(~합니다/~입니다/~있습니다)로 변환한다.

표·제목·코드 블록·인라인 코드·따옴표·링크 안은 변환하지 않는다. 변환 결과는 디프로 사람이 검토한다.
사용법: polite.py [--dry-run] [--report] FILE...
  --dry-run  파일을 바꾸지 않고 디프만 출력
  --report   규칙적이지 않은 변환 목록을 출력 (검토 대상)
"""
import difflib
import re
import sys

BASE, JONG_N, JONG_L, JONG_B = 0xAC00, 4, 8, 17
ADJ_EXACT = {'크다': '큽니다'}
ADJ_SUFFIX = {'다르다': '다릅니다', '빠르다': '빠릅니다', '느리다': '느립니다', '아니다': '아닙니다',
              '바쁘다': '바쁩니다', '아프다': '아픕니다', '이르다': '이릅니다', '흐리다': '흐립니다'}
UNCERTAIN_SUFFIX = ('르다', '쁘다', '프다')


def jong(ch):
    code = ord(ch) - BASE
    return code % 28 if 0 <= code < 11172 else None


def with_jong(ch, j):
    code = ord(ch) - BASE
    return chr(BASE + code - code % 28 + j)


def polite(word, prev):
    """word는 '다'로 끝나는 토큰. prev는 토큰 앞 글자(인라인 코드 직후 판별용)."""
    stem = word[:-1]
    if not stem:
        return '입니다'
    if word in ADJ_EXACT:
        return ADJ_EXACT[word]
    for suf, rep in ADJ_SUFFIX.items():
        if word.endswith(suf):
            return word[:-len(suf)] + rep
    # 르·으 탈락과 ㅡ 불규칙 활용은 표면형만으로 안전하게 변환할 수 없다.
    # 잘못된 문장을 만들기보다 원문을 유지해 후속 lint·사람 검토 대상으로 남긴다.
    if word.endswith(UNCERTAIN_SUFFIX):
        return word
    if word.endswith(('니다', '보다', '마다', '바다')):
        return word
    if word.endswith('는다') and len(word) > 2:
        return word[:-2] + '습니다'
    last = stem[-1]
    j = jong(last)
    if j is None:
        return stem + '입니다'
    if j == JONG_N or j == JONG_L:
        return stem[:-1] + with_jong(last, JONG_B) + '니다'
    if j:
        return stem + '습니다'
    if last == '이':
        return stem[:-1] + '입니다'
    if last == '하':
        return stem[:-1] + '합니다'
    return stem + '입니다'


END = (r'(?=\**[.!?]\**(?:\s|$)'      # 마침표 문장 끝
       r'|\**\s*$'                    # 줄 끝
       r'|\)(?:[.\s]|$)'              # 괄호 안 문장 끝
       r'|\([^)]*\)\s*\.?\s*$'        # 문장 뒤 괄호 설명
       r'|\([^)]*\)\.'
       r'|\s+→'
       r'|:)')
WORD = re.compile(r'(?<![가-힣])([가-힣]*)다' + END)
PROTECT = re.compile(r'(`[^`]*`|"[^"]*"|“[^”]*”|\'[^\']*\'|\[[^\]]*\]\([^)]*\))')


def convert_line(line):
    stripped = line.lstrip()
    if stripped.startswith(('|', '#', '<', '![')):
        return line
    spans = [m.span() for m in PROTECT.finditer(line)]

    def rep(m):
        a, b = m.span()
        if any(x < b and a < y for x, y in spans):
            return m.group(0)
        return polite(m.group(1) + '다', line[a - 1:a])
    return WORD.sub(rep, line)


def convert(text):
    lines, code = [], False
    for line in text.split('\n'):
        if line.lstrip().startswith(('```', '~~~')):
            code = not code
            lines.append(line)
            continue
        lines.append(line if code else convert_line(line))
    return '\n'.join(lines)


def is_routine(word, result):
    """검토가 필요 없는 규칙적 변환인지 여부."""
    return (word.endswith('한다') and result.endswith('합니다')) or \
        (word.endswith('된다') and result.endswith('됩니다')) or \
        (word.endswith('는다') and result.endswith('습니다')) or \
        (word.endswith('이다') and result.endswith('입니다')) or \
        word.endswith(('있다', '없다', '했다', '었다', '았다', '였다'))


def main(argv):
    dry = '--dry-run' in argv
    report = '--report' in argv
    paths = [a for a in argv if not a.startswith('--')]
    if not paths:
        print(__doc__)
        return 2
    unusual = {}
    global polite
    base = polite

    def logged(word, prev):
        result = base(word, prev)
        if result != word and not is_routine(word, result):
            unusual[(word, result)] = unusual.get((word, result), 0) + 1
        return result
    polite = logged
    for path in paths:
        with open(path, encoding='utf-8') as f:
            src = f.read()
        out = convert(src)
        if out == src:
            continue
        if dry:
            sys.stdout.writelines(difflib.unified_diff(
                src.splitlines(True), out.splitlines(True), path, path))
        else:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(out)
    if report and unusual:
        print('# 검토가 필요한 변환 (수정 전 => 수정 후, 횟수)')
        for (w, r), n in sorted(unusual.items()):
            print(f'{w} => {r} ({n})')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
