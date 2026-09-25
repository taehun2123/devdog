#!/usr/bin/env python3
"""한국어 공학 문서체 검사기.

사용법:
  kolint.py PATH...              파일·폴더 검사 (Markdown 본문, 코드 주석)
  kolint.py --commit-msg FILE    커밋 메시지 검사 (FILE 대신 - 이면 stdin)
  kolint.py --text [--as NAME]   stdin 텍스트 검사 (NAME 확장자로 종류 판별, 기본 .md)
  kolint.py --hook post|pre      Claude Code 훅 모드 (stdin JSON, stdout JSON)
옵션: --json, --config PATH
종료 코드: error 등급 위반이 있으면 1, 없으면 0. 훅 모드는 항상 0.
"""
import fnmatch
import json
import os
import re
import shlex
import sys

# ---------------------------------------------------------------- 설정

CONFIG_NAME = '.devdog.json'
DEFAULTS = {
    'docRegister': 'hapsyo',      # 문서 본문 말투: hapsyo(~입니다) | haera(~이다) | any
    'commentRegister': 'any',     # 코드 주석 말투: hapsyo | haera | any
    'commitSubject': 'noun',      # 커밋 제목: noun(명사형) | any
    'commitBody': 'bullet',       # 커밋 본문: bullet(짧은 개조식) | any
    'forbidTrailers': [],         # 커밋 메시지에서 금지할 트레일러 이름
    'exclude': [],                # 검사 제외 glob (기본 제외 목록에 추가)
    'allow': [],                  # 검사하지 않을 어구
    'rules': {},                  # 규칙별 등급: error | warn | off
}
DEFAULT_EXCLUDE = ['**/node_modules/**', '**/.git/**', '**/dist/**', '**/build/**',
                   '**/vendor/**', '**/.venv/**', '**/__pycache__/**']


def find_config(start):
    d = os.path.abspath(start)
    if not os.path.isdir(d):
        d = os.path.dirname(d)
    while True:
        p = os.path.join(d, CONFIG_NAME)
        if os.path.isfile(p):
            return p
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def load_config(start='.', path=None):
    cfg = {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
           for k, v in DEFAULTS.items()}
    path = path or find_config(start)
    cfg['_root'] = os.path.dirname(os.path.abspath(path)) if path else None
    if path:
        with open(path, encoding='utf-8') as f:
            cfg.update(json.load(f))
    cfg['exclude'] = DEFAULT_EXCLUDE + list(cfg.get('exclude', []))
    return cfg


def is_excluded(cfg, path):
    root = cfg.get('_root') or os.getcwd()
    rel = os.path.relpath(os.path.abspath(path), root).replace(os.sep, '/')
    for pat in cfg['exclude']:
        if fnmatch.fnmatch(rel, pat) or (pat.startswith('**/') and fnmatch.fnmatch(rel, pat[3:])):
            return True
    return False


# ---------------------------------------------------------------- 규칙

RULES = {
    'heading-sentence': ('error', '제목이 문장·의문문으로 끝남. 명사형 제목으로 수정'),
    'table-cell-sentence': ('error', '표 칸이 "~다" 문장으로 끝남. "~함"·"~음"·명사구로 수정'),
    'register-mix': ('error', '설정한 말투({reg})와 다른 종결어미. 말투 통일'),
    'metaphor': ('warn', '비유·대화체 어휘. 기술 용어로 수정'),
    'native-verb': ('warn', '순우리말 동작 동사. 한자어 기술 동사로 수정'),
    'plain-term': ('warn', '읽기 어려운 번역어. 쉬운 표현으로 수정'),
    'comment-narrative': ('warn', '서술형 주석 블록. 명사형 제목과 "- 항목" 형식으로 분리'),
    'filler': ('error', '정보를 더하지 않는 부연 문장. 삭제'),
    'em-dash-aside': ('warn', '긴 대시 부가 설명. 다음 문장이나 별도 항목으로 분리'),
    'particle-spacing': ('warn', '영문·코드·숫자 뒤 조사 띄어씀. 조사를 붙여 씀'),
    'commit-subject': ('error', '커밋 제목이 문장형으로 끝남. 명사형 요약으로 수정'),
    'commit-trailer': ('error', '금지된 커밋 트레일러'),
    'commit-body-separator': ('error', '커밋 제목과 본문 사이 빈 줄 누락'),
    'commit-body-style': ('error', '커밋 본문이 문장형으로 끝남. 변경 이유를 짧은 개조식으로 작성'),
    'commit-file-list': ('warn', '커밋 메시지에 파일·함수 이름 나열. 변경 대상과 이유로 작성'),
    'commit-signature': ('error', 'AI 도구 서명·공동작업 표기. 삭제'),
    'commit-emoji': ('error', '커밋 메시지에 이모지 사용. 삭제'),
    'pr-title': ('error', 'PR 제목이 문장형으로 끝남. 명사형 요약으로 수정'),
    'pr-signature': ('error', 'PR 본문의 AI 도구 서명. 삭제'),
    'pr-emoji': ('error', 'PR 제목·본문에 이모지 사용. 삭제'),
}
REGISTER_NAME = {'hapsyo': '~입니다·~하십시오', 'haera': '~이다·~한다'}

# (정규식, 권장 표현). 기술 문서에서 오탐이 잦은 어휘(곧, 떨어지다 등)는 넣지 않는다.
LEXICON = [
    (r'들고 (?:있|다니)|손에 들', '보관·유지'),
    (r'붙잡|붙들', '점유·유지'),
    (r'띄[우운워웠]', '표시·기동·실행'),
    (r'(?<![가-힣])답(?=[이을은만도]|한다|해|\s|$|[.,])', '응답'),
    (r'넘어[지진졌질]', '장애·오류'),
    (r'(?<![가-힣])죽(?:는|으면|었|인|어|을)', '종료·실패·장애'),
    (r'살아 ?(?:있|남)', '유효·활성·실행 중'),
    (r'삼[키킨켜]', '무시·누락'),
    (r'흘[려리린]', '노출·누락'),
    (r'태[운우워웠]', '처리·실행'),
    (r'먹[는히혀]|먹어', '적용·소비'),
    (r'뱉', '반환·출력'),
    (r'짚[는어고]', '측정·선택·지정'),
    (r'(?<![가-힣])(?:그린다|그려|그리는|그릴 )', '표시·렌더링'),
    (r'뜬다|뜨[면는]', '표시·기동'),
    (r'꺼[낸내]', '조회·추출'),
    (r'튕[기겨긴겼]', '거절·실패'),
    (r'헤매', '탐색 실패'),
    (r'쥐[고어]|쥔', '보유'),
    (r'박[힌혀아]', '하드코딩·고정'),
    (r'굳[는어었혀]', '확정·고정'),
    (r'[가-힣]거든', '구어체 어미 삭제'),
    (r'말(?:한다|해 ?준)', '의미한다·나타낸다'),
    (r'알아[채챈차]', '감지·발견'),
    (r'(?<![가-힣])믿[는고어]', '신뢰·가정'),
    (r'(?<!로 )(?<!라고 )부[른르](?:다|는)(?! 이름)', '호출'),
    (r'묻는다|물어(?:보|본|봐)?', '요청·조회'),
    (r'읽힌다|읽혀', '인식된다'),
    (r'튄다|튀[어었]', '급증·순간 이동'),
    (r'잡아먹', '소비·점유'),
    (r'꼴이', '형태·상태'),
    (r'(?<![가-힣])녀석', '대상'),
    (r'손[을이] (?:대|댄|댈)', '수정'),
    (r'길목', '경로·지점'),
    (r'(?<![가-힣])문턱', '기준·임계값'),
    (r'그늘|뿌리[가를]|손끝', '비유 삭제'),
    (r'흐른다|흘러간다', '처리된다·전달된다'),
    (r'통째로', '전체'),
    (r'못 ?박', '고정·검증'),
    (r'(?<![가-힣])늘 (?!수 )', '항상'),
    (r'(?<![가-힣])시험(?=[이을은에으과]|\s|$|[.,)])', '테스트'),
    (r'고른다|고르는', '선택'),
    (r'잡[았는혀힌](?:다)?|잡아낸', '발견·검출·획득'),
    (r'적는다|적어 ?[두둔놓]|적었', '입력·기록'),
    (r'막는다|막[혀힌혔]', '방지·차단(메시지 전송은 전송되지 않음)'),
    (r'(?<![가-힣])(?:돈다|돌린다|돌려 ?[보봤])', '실행'),
    (r'(?<![가-힣])돌려[주준줘줄]', '반환'),
    (r'깨[진져졌]', '실패·손상'),
    (r'터[진져졌]|터지', '오류 발생'),
    (r'갈 곳|갈림', '이동 대상·분기'),
]
LEXICON = [(re.compile(p), hint) for p, hint in LEXICON]

# 순우리말 동작 동사 → 한자어 기술 동사. '두 개'·'한 줄이'·'넘어지다' 오탐 방지를 위해 활용형만 검출
NATIVE_VERB = [
    (r'(?<![가-힣])(?:둔다|둡니다|두었|두어|둬|두면|두십시오)', '설정·배치·유지'),
    (r'늘[리린려렸립]|늘어[나난났]', '확대·증가'),
    (r'줄인다|줄였|줄여|줄입니다|줄어[들든드]', '축소·감소'),
    (r'넘는다|넘었|넘으면|넘어서|넘습니다|넘을|넘친|넘쳐', '초과'),
]
NATIVE_VERB = [(re.compile(p), hint) for p, hint in NATIVE_VERB]

# 번역어·전문어 → 읽기 쉬운 표현. '대화 → 채팅'처럼 도메인에 따라 다른 용어는 넣지 않는다
PLAIN_TERM = [
    (r'크래시', '강제 종료·비정상 종료'),
    (r'단언', '필수 조건·조건을 건 위치'),
    (r'전송(?:이|은|을)?\s?차단', '전송되지 않음·전송 실패'),
]
PLAIN_TERM = [(re.compile(p), hint) for p, hint in PLAIN_TERM]
# 주석 항목 줄: 목록·번호·인용·제목
COMMENT_ITEM = re.compile(r'^\s*(?:[-*•>#]|\d+[.)])\s')
NARRATIVE_MIN_SENTENCES = 3

FILLER = re.compile(
    r'(?:이게|이것이|그게|그것이|이상이|이 \d+[개가지]*[가이]?) 전부(?:입니다|이다|다)'
    r'|(?:이게|이것이|그게) 핵심(?:입니다|이다)'
    r'|셈(?:입니다|이다|이 된다|이 됩니다)'
    r'|(?:라고|다고) 보면 (?:된다|됩니다)'
    r'|말할 것도 없이|두말할 필요 없이')
EM_DASH = re.compile(r'\S\s*—\s*\S|[가-힣)\]]\s+[–-]{1,2}\s+[가-힣(\[`]')
HANGUL = re.compile(r'[가-힣]')
PARTICLE_SPACE = re.compile(
    r'(?:`[^`]+`|[A-Za-z0-9_])( )(?:을|를|이|가|은|는|에|의|로|으로|와|과|도|만|에서|에게|까지|부터'
    r'|처럼|이며|이고|이면|이다|이나|입니다|으로는|에는|에도|로는|와는|과는|이라|이라는|라는)(?![가-힣])')
NOUN_DA = {'바다', '판다', '소다', '보다', '마다', '과다', '최다'}
HEAD_END = re.compile(r'(?:[가-힣]다|[가-힣]까|인가|는가|은가|던가|(?<=\s)때|않게|도록|\?'
                      r'|(?<=[가-힣])(?:에|에서|으로|려면|하면|하고|해서)'
                      r'|(?<![가-힣])(?:무엇|왜|어떻게|언제|어디|누가))$')
# 문장 끝의 '~다' 토큰. polite.py의 END와 같은 경계.
DA_WORD = re.compile(r'(?<![가-힣])([가-힣]*다)(?=\**[.!?]\**(?:\s|$)|\**\s*$|\)(?:[.\s]|$)'
                     r'|\([^)]*\)\s*\.?\s*$|\([^)]*\)\.|\s+→|:)')
NIDA_WORD = re.compile(r'[가-힣]+니다(?=[.!?]?(?:\s|$|\)))')
EXAMPLE_HEADER = re.compile(r'표현|예시|예문|^예$|명사형|문장|원문|고친|피할|잘못|수정 전|수정 후|메시지|문구|before|after|message|text', re.I)
PROTECT = re.compile(r'`[^`]*`|"[^"]*"|“[^”]*”|‘[^’]*’|「[^」]*」|(?<![가-힣A-Za-z])\'[^\']*\''
                     r'|\]\([^)]*\)|https?://\S+|<[^>]+>')


def severity(cfg, rule):
    return cfg['rules'].get(rule, RULES[rule][0])


def protected_spans(line, cfg):
    spans = [m.span() for m in PROTECT.finditer(line)]
    for phrase in cfg.get('allow', []):
        start = line.find(phrase)
        while phrase and start != -1:
            spans.append((start, start + len(phrase)))
            start = line.find(phrase, start + 1)
    return spans


def free(m, spans, offset=0):
    a, b = m.start() + offset, m.end() + offset
    return not any(x < b and a < y for x, y in spans)


def is_sentence_da(word):
    return word.endswith('다') and len(word) > 1 and word not in NOUN_DA \
        and not word.endswith(('보다', '마다'))


class Finding:
    def __init__(self, rule, path, line, excerpt, sev, detail=''):
        self.rule, self.path, self.line, self.excerpt, self.sev, self.detail = \
            rule, path, line, excerpt.strip(), sev, detail

    def message(self):
        msg = RULES[self.rule][1]
        if self.rule == 'register-mix':
            return msg.format(reg=REGISTER_NAME.get(self.detail, self.detail))
        return f'{msg}: {self.detail}' if self.detail else msg

    def as_dict(self):
        return {'rule': self.rule, 'severity': self.sev, 'path': self.path, 'line': self.line,
                'message': self.message(), 'excerpt': self.excerpt}


def check_prose(text, spans, register, add, check_register=True):
    """문장 단위 규칙(말투·비유·부연·긴 대시). add(rule, detail)로 결과를 전달한다."""
    for pat, hint in LEXICON:
        for m in pat.finditer(text):
            if free(m, spans):
                add('metaphor', f'"{m.group(0).strip()}" → {hint}')
                break
    for pat, hint in NATIVE_VERB:
        for m in pat.finditer(text):
            if free(m, spans):
                add('native-verb', f'"{m.group(0)}" → {hint}')
                break
    for pat, hint in PLAIN_TERM:
        for m in pat.finditer(text):
            if free(m, spans):
                add('plain-term', f'"{m.group(0)}" → {hint}')
                break
    for m in FILLER.finditer(text):
        if free(m, spans):
            add('filler', f'"{m.group(0)}"')
            break
    for m in PARTICLE_SPACE.finditer(text):
        a, b = m.start(1), m.end()
        if not any(x < b and a < y for x, y in spans):
            add('particle-spacing', f'"{m.group(0)}"')
            break
    for m in EM_DASH.finditer(text):
        if free(m, spans):
            add('em-dash-aside', '')
            break
    if not check_register or register == 'any':
        return
    if register == 'hapsyo':
        for m in DA_WORD.finditer(text):
            if free(m, spans) and is_sentence_da(m.group(1)) and not m.group(1).endswith('니다'):
                add('register-mix', register)
                break
    elif register == 'haera':
        for m in NIDA_WORD.finditer(text):
            if free(m, spans):
                add('register-mix', register)
                break


def strip_heading(text):
    text = re.sub(r'\s*\{#[^}]*\}\s*$', '', text)
    text = re.sub(r'`[^`]*`', 'X', text)
    return re.sub(r'[\s*_.:!]+$', '', text)


def heading_violation(text):
    t = strip_heading(text)
    if not HANGUL.search(t) and not t.endswith('?'):
        return False
    if not HEAD_END.search(t):
        return False
    last = t.split()[-1] if t.split() else ''
    return last not in NOUN_DA


# ---------------------------------------------------------------- Markdown

def lint_markdown(text, path, cfg):
    out = []
    lines = text.split('\n')
    in_code = in_front = in_html_comment = False
    skip_next = False
    table_header = None
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if i == 1 and s == '---':
            in_front = True
            continue
        if in_front:
            in_front = s != '---'
            continue
        if s.startswith(('```', '~~~')):
            in_code = not in_code
            continue
        if in_code:
            continue
        if in_html_comment:
            in_html_comment = '-->' not in s
            continue
        if s.startswith('<!--'):
            in_html_comment = '-->' not in s
            if 'kolint-disable-next-line' in s:
                skip_next = True
            continue
        if skip_next:
            skip_next = False
            continue
        if s.startswith('|'):
            cells = [c.strip() for c in s.strip('|').split('|')]
            if all(re.fullmatch(r':?-{2,}:?', c) for c in cells if c):
                continue
            if table_header is None:
                table_header = cells
                continue
        else:
            table_header = None
        if 'kolint-disable-line' in line or not HANGUL.search(line):
            continue

        def add(rule, detail='', _i=i, _line=line):
            sev = severity(cfg, rule)
            if sev != 'off':
                out.append(Finding(rule, path, _i, _line, sev, detail))

        if re.match(r'#{1,6}\s', s):
            if heading_violation(re.sub(r'^#{1,6}\s+', '', s)):
                add('heading-sentence')
            check_prose(line, protected_spans(line, cfg), cfg['docRegister'], add, check_register=False)
            continue
        if table_header is not None:
            sentence_found = False
            for j, cell in enumerate(cells):
                header = table_header[j] if j < len(table_header) else ''
                if EXAMPLE_HEADER.search(header) or not HANGUL.search(cell):
                    continue
                plain = re.sub(r'[\s*_.!]+$', '', PROTECT.sub('', cell))
                words = plain.split()
                # 여러 문장으로 된 칸(런북 조치 설명 등)은 본문으로 보고 제외한다
                single = not re.search(r'[.!?](?:\s|<br>)', plain)
                if not sentence_found and single and words and is_sentence_da(words[-1]):
                    add('table-cell-sentence')
                    sentence_found = True
                check_prose(cell, protected_spans(cell, cfg), cfg['docRegister'], add, check_register=False)
            continue
        if s.startswith(('![', '<')):
            continue
        # 인용 블록은 외부 원문을 옮긴 경우가 많아 말투 검사에서 제외한다
        check_prose(line, protected_spans(line, cfg), cfg['docRegister'], add,
                    check_register=not s.startswith('>'))
    return out


# ---------------------------------------------------------------- 코드 주석

C_LIKE = {'.java', '.kt', '.kts', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.go', '.rs',
          '.swift', '.c', '.h', '.cc', '.cpp', '.hpp', '.cs', '.scala', '.dart', '.php',
          '.groovy', '.gradle', '.m', '.mm'}
HASH = {'.py', '.sh', '.bash', '.zsh', '.rb', '.yml', '.yaml', '.toml', '.r', '.pl', '.ps1'}
DASH2 = {'.sql', '.lua', '.hs'}
MARKDOWN = {'.md', '.mdx', '.markdown'}


def kind_of(path):
    base = os.path.basename(path)
    ext = os.path.splitext(base)[1].lower()
    if ext in MARKDOWN:
        return 'md'
    if ext in C_LIKE:
        return 'c'
    if ext in HASH or base in ('Dockerfile', 'Makefile'):
        return 'hash'
    if ext in DASH2:
        return 'dash'
    return None


def comment_texts(lines, kind):
    """(줄 번호, 주석 본문) 목록. 문자열 안의 주석 기호는 근사로 처리한다."""
    out = []
    in_block = False
    for i, line in enumerate(lines, 1):
        if kind == 'c':
            if in_block:
                end = line.find('*/')
                body = line if end == -1 else line[:end]
                in_block = end == -1
                out.append((i, re.sub(r'^\s*\*\s?', '', body)))
                continue
            m = re.search(r'/\*+|//+', line)
            if not m:
                continue
            if m.group(0).startswith('/*'):
                rest = line[m.end():]
                end = rest.find('*/')
                in_block = end == -1
                out.append((i, rest if end == -1 else rest[:end]))
            else:
                out.append((i, line[m.end():]))
        else:
            mark = '#' if kind == 'hash' else '--'
            pos = line.find(mark)
            while pos != -1:
                before = line[:pos]
                if before.count('"') % 2 == 0 and before.count("'") % 2 == 0:
                    if not (mark == '#' and i == 1 and line.startswith('#!')):
                        out.append((i, line[pos + len(mark):]))
                    break
                pos = line.find(mark, pos + 1)
    return out


def lint_code(text, path, cfg, kind):
    out = []
    lines = text.split('\n')
    skip = set()
    for i, line in enumerate(lines, 1):
        if 'kolint-disable-next-line' in line:
            skip.add(i + 1)
        if 'kolint-disable-line' in line:
            skip.add(i)
    for i, body in comment_texts(lines, kind):
        if i in skip or not HANGUL.search(body):
            continue

        def add(rule, detail='', _i=i):
            sev = severity(cfg, rule)
            if sev != 'off':
                out.append(Finding(rule, path, _i, lines[_i - 1], sev, detail))

        spans = protected_spans(body, cfg)
        head = re.match(r'\s*#{1,6}\s+(.*)', body)
        if head and heading_violation(head.group(1)):
            add('heading-sentence')
        check_prose(body, spans, cfg['commentRegister'], add, check_register=not head)
    out.extend(narrative_blocks(lines, kind, path, cfg, skip))
    return out


def narrative_blocks(lines, kind, path, cfg, skip):
    """항목 없이 '~다' 문장이 3개 이상인 연속 주석 블록. 블록 첫 줄에 보고한다."""
    sev = severity(cfg, 'comment-narrative')
    if sev == 'off':
        return []
    blocks = []
    for i, body in comment_texts(lines, kind):
        if blocks and blocks[-1][-1][0] == i - 1:
            blocks[-1].append((i, body))
        else:
            blocks.append([(i, body)])
    out = []
    for block in blocks:
        first = block[0][0]
        bodies = [b for _, b in block]
        if first in skip or any(COMMENT_ITEM.match(b) for b in bodies):
            continue
        sentences = sum(1 for b in bodies for m in DA_WORD.finditer(b) if is_sentence_da(m.group(1)))
        if sentences >= NARRATIVE_MIN_SENTENCES:
            out.append(Finding('comment-narrative', path, first, lines[first - 1], sev, f'{sentences}문장'))
    return out


# ---------------------------------------------------------------- 커밋 메시지

# 문장형 종결: ~다, 해요체. '필요'·'소요'처럼 '요'로 끝나는 명사는 제외한다
SENTENCE_END = re.compile(r'(?:[가-힣]다|(?:[해돼어아여워와봐세예줘져]|에)요)[.!]?$')
CONVENTIONAL = re.compile(r'^[A-Za-z]+(?:\([^)]*\))?!?:\s*')
TRAILER = re.compile(r'^[A-Za-z][A-Za-z-]*:\s')
BULLET = re.compile(r'^(?:[-*•]|\d+[.)])\s+')
FILE_TOKEN = re.compile(r'(?<![\w/.-])`?[\w./-]+\.(?:java|kt|kts|ts|tsx|js|jsx|mjs|py|go|rs|rb|php|swift|c|h|cc|cpp|'
                        r'cs|scala|dart|sql|md|json|ya?ml|toml|xml|gradle|sh|css|scss|html)`?(?![\w])')
FUNC_TOKEN = re.compile(r'(?<![\w.])[A-Za-z_]\w*\(\)')
AI_SIGNATURE = re.compile(r'🤖|Generated (?:with|by) .*(?:Claude|Copilot|ChatGPT|Codex|Cursor|Gemini)'
                          r'|^Co-Authored-By:.*(?:Claude|Copilot|ChatGPT|GPT|Codex|Cursor|Gemini|anthropic|openai)',
                          re.I)
EMOJI = re.compile('[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B50\u2B55\uFE0F]')


def lint_commit(msg, cfg, path='COMMIT_EDITMSG'):
    out = []
    # git commit -v가 붙이는 구분선 아래 디프는 메시지가 아니다
    msg = re.split(r'^# -+ >8 -+$', msg, maxsplit=1, flags=re.M)[0]
    lines = [l for l in msg.split('\n') if not l.startswith('#')]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return out

    def add(rule, line_no, detail=''):
        sev = severity(cfg, rule)
        if sev != 'off':
            out.append(Finding(rule, path, line_no, lines[line_no - 1], sev, detail))

    subject = CONVENTIONAL.sub('', lines[0].strip())
    if cfg['commitSubject'] == 'noun' and HANGUL.search(subject):
        if SENTENCE_END.search(subject) or subject.endswith(('.', '!')):
            add('commit-subject', 1)
    m = FILE_TOKEN.search(subject) or FUNC_TOKEN.search(subject)
    if m:
        add('commit-file-list', 1, f'"{m.group(0)}"')
    if len(lines) > 1 and lines[1].strip():
        add('commit-body-separator', 2)
    for n, line in enumerate(lines, 1):
        if AI_SIGNATURE.search(line):
            add('commit-signature', n)
        elif EMOJI.search(line):
            add('commit-emoji', n)
        if HANGUL.search(line):
            spans = protected_spans(line, cfg)
            check_prose(line, spans, 'any', lambda r, d='', _n=n: add(r, _n, d))
        if n == 1:
            continue
        text = line.strip()
        if not text or TRAILER.match(text):
            continue
        item = BULLET.sub('', text)
        if cfg.get('commitBody') == 'bullet' and HANGUL.search(item) and SENTENCE_END.search(item):
            add('commit-body-style', n)
        if BULLET.match(text) and FILE_TOKEN.match(item):
            add('commit-file-list', n, f'"{FILE_TOKEN.match(item).group(0)}"')
    for name in cfg.get('forbidTrailers', []):
        for n, line in enumerate(lines, 1):
            if re.match(re.escape(name) + r'\s*:', line, re.I):
                add('commit-trailer', n, name)
    return out


# ---------------------------------------------------------------- 파일·폴더

def lint_text(text, path, cfg):
    kind = kind_of(path) or 'md'
    if kind == 'md':
        return lint_markdown(text, path, cfg)
    return lint_code(text, path, cfg, kind)


def lint_file(path, cfg):
    if kind_of(path) is None or is_excluded(cfg, path):
        return []
    try:
        with open(path, encoding='utf-8') as f:
            text = f.read()
    except (UnicodeDecodeError, OSError):
        return []
    return lint_text(text, path, cfg)


def iter_files(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__')]
                for name in sorted(files):
                    yield os.path.join(root, name)
        else:
            yield p


# ---------------------------------------------------------------- 출력

def format_hook(findings, limit=3):
    by_rule = {}
    for f in findings:
        by_rule.setdefault(f.rule, []).append(f)
    parts = ['DevDog: 다음 위치의 문체 규칙 위반을 수정하십시오. 나머지 문장은 수정하지 마십시오.']
    for rule, items in by_rule.items():
        head = items[0].message() if rule == 'register-mix' else RULES[rule][1]
        parts.append(f'[{rule}] {head}')
        for f in items[:limit]:
            detail = f' ({f.detail})' if f.detail and rule != 'register-mix' else ''
            parts.append(f'- {f.path}:{f.line}{detail}: {f.excerpt[:100]}')
        if len(items) > limit:
            parts.append(f'- 외 {len(items) - limit}곳')
    return '\n'.join(parts)


def changed_lines(text, tool_input):
    """Edit·MultiEdit가 바꾼 줄 번호 집합. Write이거나 위치를 찾지 못하면 None(전체)."""
    if 'edits' in tool_input:
        news = [e.get('new_string', '') for e in tool_input['edits']]
    elif 'new_string' in tool_input:
        news = [tool_input['new_string']]
    else:
        return None
    lines = set()
    for new in news:
        if not new:
            continue
        start = text.find(new)
        if start == -1:
            return None
        while start != -1:
            first = text.count('\n', 0, start) + 1
            lines.update(range(first, first + new.count('\n') + 1))
            start = text.find(new, start + 1)
    return lines


def hook_post(data):
    ti = data.get('tool_input') or {}
    path = ti.get('file_path')
    if not path or not os.path.isfile(path) or kind_of(path) is None:
        return {}
    cfg = load_config(path)
    findings = lint_file(path, cfg)
    if not findings:
        return {}
    with open(path, encoding='utf-8') as f:
        scope = changed_lines(f.read(), ti)
    if scope is not None:
        findings = [f for f in findings if f.line in scope]
    if not findings:
        return {}
    msg = format_hook(findings)
    if any(f.sev == 'error' for f in findings):
        return {'decision': 'block', 'reason': msg}
    return {'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': msg}}


HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?\n(.*?)\n\s*\1\s*(?:\n|$)", re.S)


def commit_messages(cmd, cwd):
    """git commit 명령에서 -m·--message·-F 값을 추출한다. 찾지 못하면 빈 목록."""
    try:
        tokens = shlex.split(cmd, posix=True)
    except ValueError:
        return []
    msgs = []
    for idx, tok in enumerate(tokens):
        if tok != 'commit' or 'git' not in tokens[:idx]:
            continue
        j = idx + 1
        while j < len(tokens) and tokens[j] not in ('&&', '||', ';', '|'):
            t = tokens[j]
            value = None
            if t in ('-m', '--message') or (re.fullmatch(r'-[a-zA-Z]*m', t) and t != '-m'):
                value = tokens[j + 1] if j + 1 < len(tokens) else None
                j += 1
            elif t.startswith('--message='):
                value = t.split('=', 1)[1]
            elif re.fullmatch(r'-m.+', t):
                value = t[2:]
            elif t in ('-F', '--file') and j + 1 < len(tokens):
                value = read_arg_file(tokens[j + 1], cmd, cwd)
                j += 1
            if value is not None:
                msgs.append(unwrap_heredoc(value))
            j += 1
    return msgs


def unwrap_heredoc(value):
    """"$(cat <<'EOF' ... EOF)" 형태의 인자에서 본문만 꺼낸다."""
    m = re.match(r"\$\(cat\s*" + HEREDOC.pattern + r"\s*\)$", value, re.S)
    return m.group(2) if m else value


def read_arg_file(target, cmd, cwd):
    """-F 인자의 파일 내용. '-'이면 명령의 heredoc 본문."""
    if target == '-':
        m = HEREDOC.search(cmd)
        return m.group(2) if m else None
    path = os.path.join(cwd, target)
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as f:
            return f.read()
    return None


def pr_fields(cmd, cwd):
    """gh pr create·edit 명령의 (제목, 본문). 해당 명령이 아니면 None."""
    try:
        tokens = shlex.split(cmd, posix=True)
    except ValueError:
        return None
    for idx in range(len(tokens) - 2):
        if tokens[idx:idx + 2] != ['gh', 'pr'] or tokens[idx + 2] not in ('create', 'edit'):
            continue
        title = body = None
        j = idx + 3
        while j < len(tokens) and tokens[j] not in ('&&', '||', ';', '|'):
            t = tokens[j]
            nxt = tokens[j + 1] if j + 1 < len(tokens) else ''
            if t in ('-t', '--title'):
                title, j = unwrap_heredoc(nxt), j + 1
            elif t.startswith('--title='):
                title = unwrap_heredoc(t.split('=', 1)[1])
            elif t in ('-b', '--body'):
                body, j = unwrap_heredoc(nxt), j + 1
            elif t.startswith('--body='):
                body = unwrap_heredoc(t.split('=', 1)[1])
            elif t in ('-F', '--body-file'):
                body, j = read_arg_file(nxt, cmd, cwd), j + 1
            elif t.startswith('--body-file='):
                body = read_arg_file(t.split('=', 1)[1], cmd, cwd)
            j += 1
        return title, body
    return None


def lint_pr(title, body, cfg):
    """PR 제목은 커밋 제목 규칙, 본문은 Markdown 규칙과 서명·이모지 금지를 적용한다."""
    out = []

    def add(rule, where, line_no, text):
        sev = severity(cfg, rule)
        if sev != 'off':
            out.append(Finding(rule, where, line_no, text, sev))

    if title:
        subject = CONVENTIONAL.sub('', title.strip())
        if cfg['commitSubject'] == 'noun' and HANGUL.search(subject) and \
                (SENTENCE_END.search(subject) or subject.endswith(('.', '!'))):
            add('pr-title', 'PR 제목', 1, title)
        if EMOJI.search(title):
            add('pr-emoji', 'PR 제목', 1, title)
    if body:
        for n, line in enumerate(body.split('\n'), 1):
            if AI_SIGNATURE.search(line):
                add('pr-signature', 'PR 본문', n, line)
            elif EMOJI.search(line):
                add('pr-emoji', 'PR 본문', n, line)
        # PR 본문은 개조식이 많으므로 말투 검사는 하지 않는다
        out += lint_markdown(body, 'PR 본문', dict(cfg, docRegister='any'))
    return out


def hook_pre(data):
    cmd = (data.get('tool_input') or {}).get('command', '')
    is_commit = re.search(r'\bgit\b.*\bcommit\b', cmd, re.S)
    is_pr = re.search(r'\bgh\s+pr\s+(?:create|edit)\b', cmd)
    if not (is_commit or is_pr):
        return {}
    cwd = data.get('cwd') or os.getcwd()
    cfg = load_config(cwd)
    findings = []
    if is_commit:
        msgs = commit_messages(cmd, cwd)
        if msgs:
            findings += lint_commit('\n\n'.join(msgs), cfg)
    if is_pr:
        fields = pr_fields(cmd, cwd)
        if fields:
            findings += lint_pr(fields[0], fields[1], cfg)
    findings = [f for f in findings if f.sev == 'error']
    if not findings:
        return {}
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                   'permissionDecisionReason': format_hook(findings)}}


def main(argv):
    args = list(argv)
    as_json = '--json' in args
    if as_json:
        args.remove('--json')
    cfg_path = None
    if '--config' in args:
        k = args.index('--config')
        cfg_path = args[k + 1]
        del args[k:k + 2]
    if args[:1] == ['--hook']:
        try:
            data = json.load(sys.stdin)
            result = hook_post(data) if args[1] == 'post' else hook_pre(data)
        except Exception as e:  # 훅 오류로 작업을 막지 않는다
            result = {'systemMessage': f'DevDog 훅 오류: {e}'}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args[:1] == ['--commit-msg']:
        src = args[1] if len(args) > 1 else '-'
        if src == '-':
            text = sys.stdin.read()
        else:
            with open(src, encoding='utf-8') as f:
                text = f.read()
        cfg = load_config('.', cfg_path)
        findings = lint_commit(text, cfg, src)
    elif args[:1] == ['--text']:
        name = args[args.index('--as') + 1] if '--as' in args else 'stdin.md'
        cfg = load_config('.', cfg_path)
        findings = lint_text(sys.stdin.read(), name, cfg)
    else:
        if not args:
            print(__doc__)
            return 2
        cfg = load_config(args[0], cfg_path)
        findings = [f for p in iter_files(args) for f in lint_file(p, cfg)]
    if as_json:
        print(json.dumps([f.as_dict() for f in findings], ensure_ascii=False, indent=2))
    else:
        for f in findings:
            print(f'{f.path}:{f.line}: {f.sev} [{f.rule}] {f.message()}: {f.excerpt[:120]}')
    return 1 if any(f.sev == 'error' for f in findings) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
