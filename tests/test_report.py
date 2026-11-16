import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import kolint  # noqa: E402
import report  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')
SAMPLE = os.path.join(ROOT, 'skills', 'report', 'examples', 'sample.md')

DOC = """---
title: 운영 보고서
subtitle: "2026년 3분기"
---

# 요약 {.front}

::: summary
- 가용성은 99.95%를 기록할 전망이다.
  - 복구 시간 단축
:::

# 운영 현황

## 지표 점검

### 가용성

**가용성은 상승할 전망이다.** 근거 문장[^a].

**배포 횟수는 유지될 전망이다.** 근거 문장.

일반 문단.

::: figure 가용성 추이 | 가용성 회복
```json
{"x": ["1월", "2월"], "series": [{"name": "가용성", "values": [99.9, 99.95]}]}
```
자료: 모니터링
:::

::: figure 장애 건수
```json
{"type": "bar", "x": ["1월", "2월"], "series": [{"name": "건수", "values": [3, 1]}]}
```
:::

::: box 장애 조치 결과
**전환 시간은 40초이다.** 상세.
:::

## 비용 전망

**비용은 감소할 전망이다.** 근거[^b].

::: table 비용
| 항목 | 값 |
|---|---|
| 컴퓨팅 | 53 |
주: 천 달러
:::

[^a]: 첫 번째 각주
[^b]: 두 번째 각주

# 부록 {.appendix}

본문.
"""


class Blocks(unittest.TestCase):
    def test_front_matter_and_heading_attr(self):
        meta, body = report.front_matter(DOC)
        self.assertEqual(meta['subtitle'], '2026년 3분기')
        blocks = report.parse_blocks(body.splitlines())
        self.assertEqual(blocks[0], ('heading', 1, '요약', 'front'))

    def test_list_nesting(self):
        r = report.Report('- 가\n  - 나\n  - 다\n- 라\n')
        self.assertIn('<ul><li>가<ul><li>나</li><li>다</li></ul></li><li>라</li></ul>', ''.join(r.chunks))

    def test_unclosed_and_unknown_container(self):
        with self.assertRaises(report.ReportError):
            report.Report('::: box 제목\n본문\n')
        with self.assertRaises(report.ReportError):
            report.Report('::: chartbox\n본문\n:::\n')

    def test_angle_text_is_not_html(self):
        r = report.Report('<국내 성장률 전망> 표 제목\n')
        self.assertIn('&lt;국내 성장률 전망&gt;', ''.join(r.chunks))

    def test_inline(self):
        self.assertEqual(report.inline('**굵게** `a<b` {{주}} ^e^ <x>'),
                         '<strong>굵게</strong> <code>a&lt;b</code> <small class="aside">주</small> <sup>e</sup> &lt;x&gt;')


class Render(unittest.TestCase):
    def setUp(self):
        self.r = report.Report(DOC)
        self.html = self.r.html({'c-1': 5, 'c-2': 7, 'p-1': 4})

    def test_numbering(self):
        self.assertIn('<span class="pnum">1-1.</span>', self.html)
        self.assertIn('<span class="pnum">1-2.</span>', self.html)
        self.assertIn('<span class="pnum">2-1.</span>', self.html)
        self.assertNotIn('1-3.', self.html)
        self.assertIn('[그림 1.1] 가용성 추이', self.html)
        self.assertIn('[그림 1.2] 장애 건수', self.html)
        self.assertIn('[표 2.1] 비용', self.html)
        self.assertIn('<span class="box-label">Box 1</span>', self.html)

    def test_figures_paired(self):
        self.assertEqual(self.html.count('<div class="fig-row">'), 1)
        self.assertEqual(self.html.count('<div class="fig">'), 2)

    def test_footnotes_per_chapter(self):
        self.assertIn('<sup class="fn">1)</sup>', self.html)
        notes = re.findall(r'<div class="footnotes">(.*?)</div>', self.html)
        self.assertEqual(len(notes), 2)
        self.assertIn('두 번째 각주', notes[1])
        self.assertIn('<sup>1)</sup>', notes[1])

    def test_toc_and_divider(self):
        kinds = [t[0] for t in self.r.toc]
        self.assertEqual(kinds, ['front', 'part', 'chapter', 'section', 'box', 'chapter', 'front'])
        self.assertIn('<span class="pg">5</span>', self.html)
        self.assertIn('class="divider" id="p-1"', self.html)
        self.assertIn('1. 지표 점검</span><span class="dots"></span><span class="pg">5</span>', self.html)
        self.assertIn('<div class="toc-sep"></div>', self.html)

    def test_missing_footnote(self):
        with self.assertRaises(report.ReportError):
            report.Report('본문[^x].\n')


class Chart(unittest.TestCase):
    def test_ticks_cover_range(self):
        for lo, hi in ((99.82, 99.97), (0, 6), (-3.2, 4.1), (0, 0)):
            t = report.nice_ticks(lo, hi)
            self.assertLessEqual(t[0], lo)
            self.assertGreaterEqual(t[-1], hi)

    def test_line_and_bar(self):
        svg = report.chart_svg({'x': ['a', 'b', 'c'], 'series': [
            {'name': '선', 'values': [1, None, 3]},
            {'name': '막대', 'type': 'bar', 'values': [2, -1, 4]}]})
        self.assertEqual(svg.count('<rect'), 3 + 1)  # 막대 3개 + 범례 1개
        self.assertEqual(svg.count('<circle'), 2)    # None으로 끊긴 선 구간
        self.assertIn('class="c-zero"', svg)

    def test_stacked_and_shade(self):
        svg = report.chart_svg({'type': 'bar', 'stacked': True, 'x': ['1', '2'], 'shade': {'from': '2', 'label': '전망'},
                                'series': [{'values': [1, 2]}, {'values': [3, 4]}]})
        self.assertIn('fill="#dce6f2"', svg)
        self.assertIn('>전망<', svg)

    def test_invalid(self):
        with self.assertRaises(report.ReportError):
            report.chart_svg({'x': ['a', 'b'], 'series': [{'values': [1]}]})
        with self.assertRaises(report.ReportError):
            report.chart_svg({'x': ['a'], 'series': [{'type': 'pie', 'values': [1]}]})


class PageMap(unittest.TestCase):
    def test_nested_page_tree(self):
        pdf = (b'1 0 obj\n<</Type /Catalog /Pages 2 0 R /Dests 9 0 R>>\nendobj\n'
               b'2 0 obj\n<</Type /Pages /Count 3 /Kids [3 0 R 4 0 R]>>\nendobj\n'
               b'3 0 obj\n<</Type /Pages /Count 2 /Kids [5 0 R 6 0 R]>>\nendobj\n'
               b'4 0 obj\n<</Type /Page /Parent 2 0 R>>\nendobj\n'
               b'5 0 obj\n<</Type /Page /Parent 3 0 R>>\nendobj\n'
               b'6 0 obj\n<</Type /Page /Parent 3 0 R /Contents 7 0 R>>\nendobj\n'
               b'7 0 obj\n<</Length 6>> stream\nendobj\nendstream\nendobj\n'
               b'9 0 obj\n<</c-1 [6 0 R /XYZ 6 800 0]\n/p-1 [4 0 R /XYZ 6 800 0]>>\nendobj\n')
        self.assertEqual(report.page_map(pdf), {'c-1': 2, 'p-1': 3})

    def test_not_pdf(self):
        self.assertEqual(report.page_map(b'plain text'), {})


class Sample(unittest.TestCase):
    def test_sample_builds_and_passes_lint(self):
        with open(SAMPLE, encoding='utf-8') as f:
            r = report.Report(f.read(), os.path.dirname(SAMPLE))
        self.assertIn('[그림 2.1]', r.html())
        cfg = kolint.load_config(SAMPLE)
        self.assertEqual(cfg['docRegister'], 'haera')
        self.assertEqual([f.as_dict() for f in kolint.lint_file(SAMPLE, cfg)], [])

    @unittest.skipUnless(os.environ.get('DEVDOG_REPORT_E2E') and report.find_chrome(), 'DEVDOG_REPORT_E2E=1과 Chrome 필요')
    def test_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, 'sample.pdf')
            _, pages = report.build(SAMPLE, out, os.path.join(tmp, 'sample.html'))
            self.assertGreater(os.path.getsize(out), 10000)
            self.assertEqual(pages['p-1'] + 1, pages['c-1'])
            with open(os.path.join(tmp, 'sample.html'), encoding='utf-8') as f:
                self.assertIn(f'<span class="pg">{pages["c-1"]}</span>', f.read())


if __name__ == '__main__':
    unittest.main()
