#!/usr/bin/env python3
"""Markdown 보고서를 PDF로 변환한다. 표지·차례·간지·번호 문단·Box·그림·표 형식을 적용한다.

사용법:
  python3 report.py report.md -o report.pdf          # PDF 생성 (Chrome·Edge·Chromium 필요)
  python3 report.py report.md --html report.html     # HTML만 생성
  python3 report.py report.md -o report.pdf --chrome /path/to/chrome

PDF는 두 번 렌더링한다. 첫 번째 PDF의 /Dests에서 제목별 쪽 번호를 읽어 차례에 기록한다.
"""
import argparse
import html
import json
import math
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CSS_PATH = os.path.join(HERE, 'report.css')
ROMAN = ['Ⅰ', 'Ⅱ', 'Ⅲ', 'Ⅳ', 'Ⅴ', 'Ⅵ', 'Ⅶ', 'Ⅷ', 'Ⅸ', 'Ⅹ']
PALETTE = ['#1f3864', '#c00000', '#8eaadb', '#00a07a', '#ed7d31', '#7f7f7f']


# 앞부분 layout 값
# - report: 단원 간지 쪽, 장마다 새 쪽 (경제전망보고서 기본)
# - compact: 간지·장별 쪽 나눔 생략. 20쪽 이하 제출 문서의 빈 쪽 축소
LAYOUTS = ('report', 'compact')


class ReportError(ValueError):
    pass


# ---------------------------------------------------------------- Markdown 블록

CONTAINER = re.compile(r'^:::\s*([A-Za-z]+)\s*(.*?)\s*$')
HEADING = re.compile(r'^(#{1,4})\s+(.*?)\s*(?:\{\.([\w-]+)\})?\s*$')
LIST_ITEM = re.compile(r'^(\s*)([-*+]|\d+[.)])\s+(.*)$')
FOOTDEF = re.compile(r'^\[\^([^\]]+)\]:\s*(.*)$', re.M)
TABLE_SEP = re.compile(r'^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?$')
HTML_TAG = re.compile(r'^</?[A-Za-z][\w-]*[\s>/]')
NUMERIC = re.compile(r'^[-+−]?[\d,]*\.?\d+\s*%?p?$|^\[[-+]?[\d.]+\]$|^[-−]$')


def front_matter(text):
    """맨 앞 --- 구간의 key: value 목록과 나머지 본문."""
    meta = {}
    lines = text.splitlines()
    if lines and lines[0].strip() == '---':
        for i in range(1, len(lines)):
            if lines[i].strip() == '---':
                for line in lines[1:i]:
                    key, sep, value = line.partition(':')
                    if sep:
                        meta[key.strip()] = value.strip().strip('"\'')
                return meta, '\n'.join(lines[i + 1:])
    return meta, text


def split_row(line):
    s = line.strip()
    if s.startswith('|'):
        s = s[1:]
    if s.endswith('|') and not s.endswith('\\|'):
        s = s[:-1]
    return [c.strip().replace('\\|', '|') for c in re.split(r'(?<!\\)\|', s)]


def starts_block(s):
    return (s.startswith(('#', '|', ':::', '```')) or LIST_ITEM.match(s) is not None
            or HTML_TAG.match(s) is not None)


def parse_blocks(lines):
    """줄 목록을 블록 목록으로 변환한다. 컨테이너는 내부 줄을 그대로 보관한다."""
    blocks, i, n = [], 0, len(lines)
    while i < n:
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1
            continue
        if s.startswith('```'):
            j = i + 1
            while j < n and not lines[j].strip().startswith('```'):
                j += 1
            blocks.append(('code', s[3:].strip(), '\n'.join(lines[i + 1:j])))
            i = j + 1
            continue
        m = CONTAINER.match(s)
        if m:
            depth, j = 1, i + 1
            while j < n:
                t = lines[j].strip()
                if CONTAINER.match(t):
                    depth += 1
                elif t == ':::':
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if depth:
                raise ReportError(f'{i + 1}행: ::: {m.group(1)} 블록을 닫는 ::: 줄 누락')
            blocks.append(('container', m.group(1).lower(), m.group(2), lines[i + 1:j], i + 1))
            i = j + 1
            continue
        m = HEADING.match(s)
        if m:
            blocks.append(('heading', len(m.group(1)), m.group(2), m.group(3) or ''))
            i += 1
            continue
        if HTML_TAG.match(s):
            j = i
            while j < n and lines[j].strip():
                j += 1
            blocks.append(('html', '\n'.join(lines[i:j])))
            i = j
            continue
        if s.startswith('|'):
            j = i
            while j < n and lines[j].strip().startswith('|'):
                j += 1
            blocks.append(('table', [split_row(x) for x in lines[i:j]]))
            i = j
            continue
        if re.match(r'^(-{3,}|\*{3,})$', s):
            blocks.append(('hr',))
            i += 1
            continue
        if LIST_ITEM.match(line):
            items, j = [], i
            while j < n and lines[j].strip():
                m = LIST_ITEM.match(lines[j])
                if m:
                    indent = len(m.group(1).replace('\t', '    '))
                    items.append([indent // 2, m.group(2)[0].isdigit(), m.group(3)])
                elif items:
                    items[-1][2] += '\n' + lines[j].strip()
                j += 1
            blocks.append(('list', items))
            i = j
            continue
        j = i
        while j < n and lines[j].strip() and (j == i or not starts_block(lines[j].strip())):
            j += 1
        blocks.append(('para', lines[i:j]))
        i = j
    return blocks


# ---------------------------------------------------------------- 인라인

def attr(s):
    return html.escape(s, quote=True)


def inline(s, footnote=None):
    """굵게·기울임·코드·링크·^위첨자^·{{작은 글씨}}·[^각주] 변환."""
    codes = []

    def keep(m):
        codes.append(m.group(1))
        return f'\x00{len(codes) - 1}\x00'

    s = re.sub(r'`([^`]+)`', keep, s)
    s = html.escape(s, quote=False)
    s = re.sub(r'\[([^\]^][^\]]*)\]\(([^)\s]+)\)', lambda m: f'<a href="{attr(m.group(2))}">{m.group(1)}</a>', s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'(?<![*\w])\*(?![\s*])(.+?)(?<!\s)\*(?![*\w])', r'<em>\1</em>', s)
    s = re.sub(r'\{\{(.+?)\}\}', r'<small class="aside">\1</small>', s)
    if footnote:
        s = re.sub(r'\[\^([^\]]+)\]', lambda m: footnote(m.group(1)), s)
    s = re.sub(r'\^([^\s^\]]+)\^', r'<sup>\1</sup>', s)
    return re.sub('\x00(\\d+)\x00', lambda m: f'<code>{html.escape(codes[int(m.group(1))])}</code>', s)


def join_lines(lines):
    """문단 줄을 공백으로 결합한다. 끝에 공백 2개나 \\가 있으면 줄바꿈."""
    out = ''
    for k, raw in enumerate(lines):
        brk = raw.endswith('  ') or raw.rstrip().endswith('\\')
        text = raw.strip().rstrip('\\').strip()
        out += text + ('\x01' if brk and k < len(lines) - 1 else ' ')
    return out.strip()


# ---------------------------------------------------------------- 차트

def nice_ticks(lo, hi, count=5):
    if lo == hi:
        lo, hi = lo - 1, hi + 1
    raw = (hi - lo) / count
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw - 1e-12)
    first = math.floor(lo / step + 1e-9)
    ticks = [round(first * step, 10)]
    while ticks[-1] < hi - step * 1e-6 or len(ticks) < 2:
        ticks.append(round((first + len(ticks)) * step, 10))
    return ticks


def fmt_num(v):
    return ('%.2f' % v).rstrip('0').rstrip('.') if v != int(v) else str(int(v))


def chart_svg(spec):
    """JSON 차트 정의를 SVG 문자열로 변환한다. 선·막대(묶음·누적)·전망 음영을 지원한다."""
    if not isinstance(spec, dict) or not isinstance(spec.get('x'), list) or not spec.get('series'):
        raise ReportError('차트 정의에 x 목록과 series 목록 필요')
    xs, series = [str(v) for v in spec['x']], spec['series']
    kind, stacked = spec.get('type', 'line'), bool(spec.get('stacked'))
    for s in series:
        if len(s.get('values', [])) != len(xs):
            raise ReportError(f'차트 계열 "{s.get("name", "")}" 값 개수 {len(s.get("values", []))}개, x 개수 {len(xs)}개로 불일치')
        if s.get('type', kind) not in ('line', 'bar'):
            raise ReportError(f'지원하지 않는 차트 종류: {s.get("type", kind)}')
    bars = [s for s in series if s.get('type', kind) == 'bar']
    lines = [s for s in series if s.get('type', kind) == 'line']
    vals = [v for s in lines for v in s['values'] if v is not None]
    if stacked and bars:
        for k in range(len(xs)):
            col = [s['values'][k] or 0 for s in bars]
            vals += [sum(v for v in col if v > 0), sum(v for v in col if v < 0)]
    else:
        vals += [v for s in bars for v in s['values'] if v is not None]
    if bars:
        vals.append(0)
    if not vals:
        raise ReportError('차트 값 없음')
    lo = spec.get('yMin', min(vals))
    hi = spec.get('yMax', max(vals))
    if hi < lo:
        raise ReportError(f'차트 yMax({hi})가 yMin({lo})보다 작음')
    ticks = nice_ticks(lo, hi)
    lo, hi = ticks[0], ticks[-1]

    W, H, L, R, T, B = 480, 300, 44, 12, 40, 34
    pw, ph, n = W - L - R, H - T - B, len(xs)
    band = pw / n

    def px(k):
        return L + band * (k + 0.5)

    def py(v):
        return T + ph * (hi - v) / (hi - lo)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" class="chart" role="img">']
    shade = spec.get('shade')
    if shade and shade.get('from') in xs:
        x0 = L + band * xs.index(shade['from'])
        out.append(f'<rect x="{x0:.1f}" y="{T}" width="{L + pw - x0:.1f}" height="{ph}" fill="#dce6f2"/>')
        if shade.get('label'):
            out.append(f'<text x="{L + pw - 4}" y="{T + 13}" text-anchor="end" class="c-shade">{attr(shade["label"])}</text>')
    for t in ticks:
        y = py(t)
        out.append(f'<line x1="{L}" x2="{L + pw}" y1="{y:.1f}" y2="{y:.1f}" class="c-grid"/>')
        out.append(f'<text x="{L - 5}" y="{y + 4:.1f}" text-anchor="end" class="c-tick">{fmt_num(t)}</text>')
    if lo < 0 < hi:
        out.append(f'<line x1="{L}" x2="{L + pw}" y1="{py(0):.1f}" y2="{py(0):.1f}" class="c-zero"/>')
    out.append(f'<line x1="{L}" x2="{L + pw}" y1="{T + ph}" y2="{T + ph}" class="c-axis"/>')
    step = max(1, math.ceil(n / 12))
    for k, label in enumerate(xs):
        if k % step == 0:
            out.append(f'<text x="{px(k):.1f}" y="{T + ph + 15}" text-anchor="middle" class="c-tick">{attr(label)}</text>')
    if spec.get('unit'):
        out.append(f'<text x="4" y="{T - 8}" class="c-unit">({attr(spec["unit"])})</text>')

    colors = {id(s): s.get('color') or PALETTE[k % len(PALETTE)] for k, s in enumerate(series)}
    group = band * 0.7
    if bars:
        width = group if stacked else group / len(bars)
        for k in range(n):
            pos = neg = 0.0
            for b, s in enumerate(bars):
                v = s['values'][k]
                if v is None:
                    continue
                if stacked:
                    base = pos if v >= 0 else neg
                    top = base + v
                    pos, neg = (top, neg) if v >= 0 else (pos, top)
                    x = px(k) - width / 2
                    y0, y1 = py(max(base, top)), py(min(base, top))
                else:
                    x = px(k) - group / 2 + width * b
                    y0, y1 = py(max(v, 0)), py(min(v, 0))
                out.append(f'<rect x="{x:.1f}" y="{y0:.1f}" width="{max(width - 1, 1):.1f}" '
                           f'height="{max(y1 - y0, 0.5):.1f}" fill="{colors[id(s)]}"/>')
    for s in lines:
        seg, segs = [], []
        for k, v in enumerate(s['values']):
            if v is None:
                segs.append(seg)
                seg = []
            else:
                seg.append(f'{px(k):.1f},{py(v):.1f}')
        segs.append(seg)
        dash = ' stroke-dasharray="5 3"' if s.get('dashed') else ''
        for seg in segs:
            if len(seg) > 1:
                out.append(f'<polyline points="{" ".join(seg)}" fill="none" stroke="{colors[id(s)]}" stroke-width="2"{dash}/>')
            elif seg:
                cx, cy = seg[0].split(',')
                out.append(f'<circle cx="{cx}" cy="{cy}" r="2.5" fill="{colors[id(s)]}"/>')
    x = L + 6
    for s in series:
        name = str(s.get('name', ''))
        if not name:
            continue
        c = colors[id(s)]
        mark = (f'<rect x="{x}" y="{T - 30}" width="10" height="8" fill="{c}"/>' if s in bars else
                f'<line x1="{x}" x2="{x + 12}" y1="{T - 26}" y2="{T - 26}" stroke="{c}" stroke-width="2.5"/>')
        out.append(mark + f'<text x="{x + 16}" y="{T - 22}" class="c-legend">{attr(name)}</text>')
        # 범례 폭 추정: 한글 12, 라틴 7 단위
        x += 28 + sum(12 if ord(ch) > 0x2E80 else 7 for ch in name)
    out.append('</svg>')
    return ''.join(out)


# ---------------------------------------------------------------- 렌더링

class Report:
    """블록을 HTML 조각으로 변환하고 차례·간지 항목을 수집한다."""

    def __init__(self, text, base_dir='.'):
        self.meta, body = front_matter(text)
        if self.meta.get('layout', 'report') not in LAYOUTS:
            raise ReportError(f'layout 값 오류: {self.meta["layout"]} (허용: {", ".join(LAYOUTS)})')
        self.compact = self.meta.get('layout') == 'compact'
        self.base = base_dir
        self.fn_defs = {m.group(1): m.group(2) for m in FOOTDEF.finditer(body)}
        body = FOOTDEF.sub('', body)
        self.toc = []          # (kind, id, label, title)
        self.children = {}     # part id → chapter 항목
        self.chunks = []
        self.part_id = None
        self.counts = {'part': 0, 'chapter': 0, 'front': 0, 'sec': 0, 'box': 0, 'note': 0}
        self.section = None    # None | 'front' | 'chapter'
        self.reset_local()
        self.render(parse_blocks(body.splitlines()), top=True)
        self.close_section()

    def reset_local(self):
        self.para = self.fig = self.tab = 0
        self.fn_num, self.fn_notes = {}, []

    def footnote(self, key):
        if key not in self.fn_defs:
            raise ReportError(f'각주 정의 누락: [^{key}]')
        if key not in self.fn_num:
            self.fn_num[key] = len(self.fn_num) + 1
            self.fn_notes.append((self.fn_num[key], self.fn_defs[key]))
        return f'<sup class="fn">{self.fn_num[key]})</sup>'

    def il(self, s):
        return inline(s, self.footnote).replace('\x01', '<br>')

    def close_section(self):
        if self.fn_notes:
            notes = ''.join(f'<p><sup>{n})</sup> {inline(t)}</p>' for n, t in self.fn_notes)
            self.chunks.append(f'<div class="footnotes">{notes}</div>')
        if self.section:
            self.chunks.append('</section>')
        self.section = None
        self.reset_local()

    def label(self, kind, n):
        ch = self.counts['chapter'] if self.section == 'chapter' else 0
        return f'[{kind} {ch}.{n}]' if ch else f'[{kind} {n}]'

    # -- 블록
    def render(self, blocks, top):
        k = 0
        while k < len(blocks):
            b = blocks[k]
            if b[0] == 'container' and b[1] == 'figure':
                row = [b]
                if k + 1 < len(blocks) and blocks[k + 1][0] == 'container' and blocks[k + 1][1] == 'figure':
                    row.append(blocks[k + 1])
                self.chunks.append('<div class="fig-row">' + ''.join(self.figure(f) for f in row) + '</div>')
                k += len(row)
                continue
            getattr(self, 'b_' + b[0])(b, top)
            k += 1

    def b_heading(self, b, top):
        _, level, text, cls = b
        if not top:
            self.chunks.append(f'<h4>{self.il(text)}</h4>')
            return
        if level == 1:
            self.close_section()
            if cls in ('front', 'appendix'):
                self.counts['front'] += 1
                hid = f'f-{self.counts["front"]}'
                self.section = 'front'
                self.toc.append(('front', hid, '', text))
                self.chunks.append(f'<section class="front" id="{hid}"><h1 class="front-title">{self.il(text)}</h1>')
            else:
                self.counts['part'] += 1
                n = self.counts['part']
                self.part_id = f'p-{n}'
                label = (ROMAN[n - 1] if n <= len(ROMAN) else str(n)) + '.'
                self.toc.append(('part', self.part_id, label, text))
                self.children[self.part_id] = []
                self.chunks.append(f'\x02DIVIDER:{self.part_id}\x02')
        elif level == 2 and self.section != 'front':
            self.close_section()
            self.counts['chapter'] += 1
            n = self.counts['chapter']
            entry = ('chapter', f'c-{n}', f'{n}.', text)
            self.toc.append(entry)
            if self.part_id:
                self.children[self.part_id].append(entry)
            self.section = 'chapter'
            self.chunks.append(f'<section class="chapter" id="c-{n}"><h2 class="chapter-title">'
                               f'<span class="num">{n}.</span> {self.il(text)}</h2>')
        elif level in (2, 3):
            self.counts['sec'] += 1
            sid = f's-{self.counts["sec"]}'
            if self.section == 'chapter':
                self.toc.append(('section', sid, '', text))
            self.chunks.append(f'<h3 class="sec" id="{sid}">{self.il(text)}</h3>')
        else:
            self.chunks.append(f'<h4>{self.il(text)}</h4>')

    def b_para(self, b, top):
        text = join_lines(b[1])
        if top and self.section == 'chapter' and text.startswith('**'):
            self.para += 1
            self.chunks.append(f'<p class="key"><span class="pnum">{self.counts["chapter"]}-{self.para}.</span> '
                               f'{self.il(text)}</p>')
        elif text.startswith('⇒'):
            self.chunks.append(f'<p class="conclusion">{self.il(text)}</p>')
        elif text.startswith(('※', '주:', '자료:')):
            self.chunks.append(f'<p class="note">{self.il(text)}</p>')
        else:
            self.chunks.append(f'<p>{self.il(text)}</p>')

    def b_list(self, b, top):
        out, stack = [], []
        for level, ordered, text in b[1]:
            tag = 'ol' if ordered else 'ul'
            while stack and stack[-1][0] > level:
                out.append(f'</li></{stack.pop()[1]}>')
            if stack and stack[-1][0] == level:
                out.append('</li>')
            else:
                out.append(f'<{tag}>')
                stack.append((level, tag))
            out.append(f'<li>{self.il(text.replace(chr(10), " "))}')
        while stack:
            out.append(f'</li></{stack.pop()[1]}>')
        self.chunks.append(''.join(out))

    def table_html(self, rows):
        head, body, align = [], rows, []
        if len(rows) > 1 and TABLE_SEP.match('|'.join(rows[1])):
            head, body = rows[0], rows[2:]
            align = ['center' if c.startswith(':') and c.endswith(':') else 'right' if c.endswith(':') else ''
                     for c in rows[1]]
        out = ['<table>']
        if head:
            out.append('<thead><tr>' + ''.join(f'<th>{self.il(c)}</th>' for c in head) + '</tr></thead>')
        out.append('<tbody>')
        for r in body:
            cells = []
            for i, c in enumerate(r):
                a = align[i] if i < len(align) else ''
                cls = ' class="num"' if i and not a and NUMERIC.match(c) else ''
                style = f' style="text-align:{a}"' if a else ''
                cells.append(f'<td{cls}{style}>{self.il(c)}</td>')
            out.append('<tr>' + ''.join(cells) + '</tr>')
        out.append('</tbody></table>')
        return ''.join(out)

    def b_table(self, b, top):
        self.chunks.append(self.table_html(b[1]))

    def b_code(self, b, top):
        self.chunks.append(f'<pre><code>{html.escape(b[2])}</code></pre>')

    def b_html(self, b, top):
        self.chunks.append(b[1])

    def b_hr(self, b, top):
        self.chunks.append('<hr>')

    def b_container(self, b, top):
        _, kind, arg, lines, line_no = b
        if kind == 'summary':
            self.chunks.append('<div class="summary">')
            self.render(parse_blocks(lines), top=False)
            self.chunks.append('</div>')
        elif kind in ('box', 'note'):
            self.counts[kind] += 1
            n = self.counts[kind]
            bid = f'{kind[0]}-{n}'
            name = 'Box' if kind == 'box' else '참고'
            self.toc.append((kind, bid, f'{"BOX" if kind == "box" else "참고"} {n}', arg))
            self.chunks.append(f'<div class="box" id="{bid}"><div class="box-head"><span class="box-label">'
                               f'{name} {n}</span>{self.il(arg)}</div>')
            self.render(parse_blocks(lines), top=False)
            self.chunks.append('</div>')
        elif kind == 'table':
            self.tab += 1
            body, notes = split_notes(lines)
            rows = [split_row(x) for x in body if x.strip().startswith('|')]
            raw = [x for x in body if x.strip() and not x.strip().startswith('|')]
            cap = f'<div class="tbl-cap">{self.label("표", self.tab)} {self.il(arg)}</div>' if arg else ''
            table = self.table_html(rows) if rows else '\n'.join(raw)
            self.chunks.append(f'<div class="tbl">{cap}{table}{self.notes_html(notes)}</div>')
        else:
            raise ReportError(f'{line_no}행: 지원하지 않는 블록 ::: {kind} (summary, box, note, figure, table)')

    def notes_html(self, notes):
        return ''.join(f'<p class="fig-note">{self.il(t)}</p>' for t in notes)

    def figure(self, b):
        _, _, arg, lines, line_no = b
        caption, _, headline = arg.partition('|')
        body, notes = split_notes(lines)
        spec, src = None, None
        fence = [k for k, x in enumerate(body) if x.strip().startswith('```')]
        if len(fence) >= 2:
            spec = '\n'.join(body[fence[0] + 1:fence[1]])
        for x in body:
            key, sep, value = x.strip().partition(':')
            if sep and key in ('chart', 'image'):
                src = (key, value.strip())
        if src and src[0] == 'chart':
            path = os.path.join(self.base, src[1])
            if not os.path.isfile(path):
                raise ReportError(f'{line_no}행: 차트 파일 없음: {src[1]}')
            with open(path, encoding='utf-8') as f:
                spec = f.read()
        if spec is not None:
            try:
                visual = chart_svg(json.loads(spec))
            except json.JSONDecodeError as e:
                raise ReportError(f'{line_no}행: 차트 JSON 오류: {e}')
        elif src:
            visual = f'<img src="{attr(src[1])}" alt="{attr(caption.strip())}">'
        else:
            raise ReportError(f'{line_no}행: figure 블록에 chart:, image:, ```json 중 하나 필요')
        self.fig += 1
        head = f'<div class="fig-head">{self.il(headline.strip())}</div>' if headline.strip() else ''
        cap = f'<div class="fig-cap">{self.label("그림", self.fig)} {self.il(caption.strip())}</div>'
        return f'<div class="fig">{head}{cap}{visual}{self.notes_html(notes)}</div>'

    # -- 문서
    def toc_html(self, pages):
        rows, prev = [], None
        for kind, hid, label, title in self.toc:
            if kind in ('front',) and prev not in (None, 'front'):
                rows.append('<div class="toc-sep"></div>')
            pg = pages.get(hid, '')
            lab = (f'<span class="toc-tag">{html.escape(label)}</span>' if kind in ('box', 'note')
                   else f'{html.escape(label)} ' if label else '')
            rows.append(f'<a class="toc-row toc-{kind}" href="#{hid}"><span class="t">{lab}{inline(title)}</span>'
                        f'<span class="pg">{pg}</span></a>')
            prev = kind
        return '<section class="toc"><h1>차 례</h1>' + ''.join(rows) + '</section>'

    def divider_html(self, pid, pages):
        _, _, label, title = next(t for t in self.toc if t[1] == pid)
        rows = ''.join(f'<div class="mini-row"><span>{html.escape(lab)} {inline(t)}</span><span class="dots"></span>'
                       f'<span class="pg">{pages.get(cid, "")}</span></div>'
                       for _, cid, lab, t in self.children.get(pid, []))
        mini = f'<div class="mini"><div class="mini-label">목 차</div>{rows}</div>' if rows and not self.compact else ''
        return (f'<section class="divider" id="{pid}"><div class="part-title">{html.escape(label)} {inline(title)}</div>'
                f'{mini}</section>')

    def cover_html(self):
        m = self.meta
        code = f'<div class="code">{html.escape(m["code"])}</div>' if m.get('code') else ''
        sub = f'<div class="subtitle">{html.escape(m["subtitle"])}</div>' if m.get('subtitle') else ''
        org = f'<div class="org">{html.escape(m["org"])}</div>' if m.get('org') else ''
        return (f'<section class="cover"><div class="frame">{code}<div class="bar"></div>'
                f'<h1>{html.escape(m.get("title", "보고서"))}</h1>{sub}{org}<div class="band"></div></div></section>')

    def html(self, pages=None):
        pages = {k: str(v) for k, v in (pages or {}).items()}
        body = ''.join(self.chunks)
        body = re.sub('\x02DIVIDER:(p-\\d+)\x02', lambda m: self.divider_html(m.group(1), pages), body)
        with open(CSS_PATH, encoding='utf-8') as f:
            css = f.read()
        base = pathlib.Path(os.path.abspath(self.base)).as_uri() + '/'
        toc = self.toc_html(pages) if self.meta.get('toc', 'true') != 'false' else ''
        return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><base href="{base}">'
                f'<title>{html.escape(self.meta.get("title", "보고서"))}</title><style>{css}</style></head>'
                f'<body{" class=\"compact\"" if self.compact else ""}>{self.cover_html()}{toc}{body}</body></html>')


def split_notes(lines):
    """블록 본문과 '주:'·'자료:' 줄을 분리한다."""
    body, notes = [], []
    for x in lines:
        if x.strip().startswith(('주:', '자료:')):
            notes.append(x.strip())
        else:
            body.append(x)
    return body, notes


# ---------------------------------------------------------------- PDF

def page_map(data):
    """Chrome PDF의 /Dests에서 요소 id별 쪽 번호(1부터)를 추출한다."""
    text = data.decode('latin-1')
    objs = {}
    for m in re.finditer(r'(\d+) 0 obj\b', text):
        ends = [i for i in (text.find('endobj', m.end()), text.find('stream', m.end())) if i != -1]
        objs[m.group(1)] = text[m.end():min(ends) if ends else len(text)]
    catalog = next((v for v in objs.values() if re.search(r'/Type\s*/Catalog\b', v)), None)
    if catalog is None:
        return {}
    pages_ref = re.search(r'/Pages\s+(\d+) 0 R', catalog)
    order = []

    def walk(num, depth=0):
        body = objs.get(num, '')
        kids = re.search(r'/Kids\s*\[([^\]]*)\]', body)
        if kids and re.search(r'/Type\s*/Pages\b', body) and depth < 32:
            for k in re.findall(r'(\d+) 0 R', kids.group(1)):
                walk(k, depth + 1)
        else:
            order.append(num)

    if pages_ref:
        walk(pages_ref.group(1))
    index = {num: i + 1 for i, num in enumerate(order)}
    dref = re.search(r'/Dests\s+(\d+) 0 R', catalog)
    dests = objs.get(dref.group(1), '') if dref else (re.search(r'/Dests\s*(<<.*?>>)', catalog, re.S) or [None, ''])[1]
    return {name: index[p] for name, p in re.findall(r'/([^\s/\[\]<>()]+)\s*\[\s*(\d+) 0 R', dests) if p in index}


def find_chrome(explicit=None):
    cands = [explicit, os.environ.get('CHROME_PATH')]
    if sys.platform == 'darwin':
        cands += [f'/Applications/{a}.app/Contents/MacOS/{a}' for a in ('Google Chrome', 'Chromium', 'Microsoft Edge')]
    elif os.name == 'nt':
        for base in filter(None, (os.environ.get('PROGRAMFILES'), os.environ.get('PROGRAMFILES(X86)'),
                                  os.environ.get('LOCALAPPDATA'))):
            cands += [os.path.join(base, 'Google', 'Chrome', 'Application', 'chrome.exe'),
                      os.path.join(base, 'Microsoft', 'Edge', 'Application', 'msedge.exe')]
    cands += [shutil.which(n) for n in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser',
                                        'microsoft-edge', 'chrome', 'msedge')]
    return next((c for c in cands if c and os.path.isfile(c)), None)


def print_pdf(chrome, html_path, pdf_path):
    profile = tempfile.mkdtemp(prefix='devdog-chrome-')
    cmd = [chrome, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
           '--no-pdf-header-footer', f'--user-data-dir={profile}', f'--print-to-pdf={pdf_path}',
           pathlib.Path(html_path).resolve().as_uri()]
    if os.environ.get('DEVDOG_CHROME_NO_SANDBOX'):
        cmd.insert(1, '--no-sandbox')
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180, check=False)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if not os.path.isfile(pdf_path) or os.path.getsize(pdf_path) == 0:
        raise ReportError(f'PDF 생성 실패: {chrome}')


def build(md_path, pdf_path=None, html_path=None, chrome=None):
    with open(md_path, encoding='utf-8') as f:
        report = Report(f.read(), os.path.dirname(os.path.abspath(md_path)))
    pages = {}
    if pdf_path:
        exe = find_chrome(chrome)
        if not exe:
            raise ReportError('Chrome·Edge·Chromium을 찾지 못함. --chrome 또는 CHROME_PATH로 실행 파일 경로를 지정하십시오.')
        tmp = tempfile.mkdtemp(prefix='devdog-report-')
        try:
            first_html, first_pdf = os.path.join(tmp, 'pass1.html'), os.path.join(tmp, 'pass1.pdf')
            with open(first_html, 'w', encoding='utf-8') as f:
                f.write(report.html())
            print_pdf(exe, first_html, first_pdf)
            with open(first_pdf, 'rb') as f:
                pages = page_map(f.read())
            final_html = os.path.join(tmp, 'report.html')
            with open(final_html, 'w', encoding='utf-8') as f:
                f.write(report.html(pages))
            print_pdf(exe, final_html, os.path.abspath(pdf_path))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if html_path:
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(report.html(pages))
    return report, pages


def main(argv=None):
    ap = argparse.ArgumentParser(description='Markdown 보고서를 PDF로 변환')
    ap.add_argument('source')
    ap.add_argument('-o', '--output', help='PDF 경로')
    ap.add_argument('--html', help='HTML 경로')
    ap.add_argument('--chrome', help='Chrome·Edge·Chromium 실행 파일 경로')
    args = ap.parse_args(argv)
    if not args.output and not args.html:
        args.output = os.path.splitext(args.source)[0] + '.pdf'
    try:
        _, pages = build(args.source, args.output, args.html, args.chrome)
    except (ReportError, OSError, subprocess.TimeoutExpired) as e:
        print(f'report.py: {e}', file=sys.stderr)
        return 2
    for p in filter(None, (args.output, args.html)):
        print(p)
    return 0


if __name__ == '__main__':
    sys.exit(main())
