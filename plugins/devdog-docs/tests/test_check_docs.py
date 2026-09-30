"""Regression cases for the vendored documentation checker."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / 'templates' / 'tools'))
import check_docs  # noqa: E402


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


class MarkdownCases(unittest.TestCase):
    def test_nested_paths_and_html_images(self):
        line = '[기록](2026-09-13(목록).md) ![화면](<assets/a b.png> "제목")'
        self.assertEqual(list(check_docs.markdown_links(line)), [
            (False, '기록', '2026-09-13(목록).md'), (True, '화면', 'assets/a b.png')])
        self.assertEqual(list(check_docs.html_links('<td><img src="../a.png" alt="화면"/></td>')),
                         [(True, '화면', '../a.png')])

    def test_long_fenced_example_is_not_a_link(self):
        text = '# 문서\n````markdown\n# 예시\n```bash\n[예시](missing.md)\n```\n````\n[본문](real.md)'
        lines = [line for _, line, _, _ in check_docs.prose_lines(text)]
        self.assertNotIn('[예시](missing.md)', lines)
        self.assertIn('[본문](real.md)', lines)

    def test_korean_and_repeated_anchors(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'page.md'
            write(path, '# 런북\n## 서버 확인\n## 서버 확인\n')
            self.assertEqual(check_docs.anchors(path), {'런북', '서버-확인', '서버-확인-1'})


class SingleLayout(unittest.TestCase):
    """Single repository: docs/human, docs/ai, config at the root."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / 'app'
        (self.repo / 'scripts').mkdir(parents=True)
        shutil.copy(check_docs.__file__, str(self.repo / 'scripts' / 'check_docs.py'))
        write(self.repo / 'docs.config.json', json.dumps({
            'schema_version': 1, 'layout': 'single', 'project': {'name': 'App', 'language': 'ko'},
            'repositories': {'app': {'local': '.', 'url': 'https://github.com/example/app', 'branch': 'main'}}}))
        write(self.repo / 'README.md', '# 앱\n\n[목록](catalog.json)\n')
        write(self.repo / 'docs/human/README.md', '# 사람용 문서\n')
        write(self.repo / 'docs/ai/sources.json', json.dumps({
            'sources': [{'id': 'start', 'repository': 'app', 'path': 'README.md'}]}))

    def tearDown(self):
        self.temp.cleanup()

    def check(self, *args):
        return subprocess.run([sys.executable, str(self.repo / 'scripts' / 'check_docs.py')] + list(args),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

    def test_first_catalog_and_stale_catalog(self):
        result = self.check('--write-catalog')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        catalog = json.loads((self.repo / 'catalog.json').read_text(encoding='utf-8'))
        self.assertEqual([d['path'] for d in catalog['documents']], ['README.md', 'docs/human/README.md'])
        write(self.repo / 'docs/human/how-to/new.md', '# 새 문서\n')
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('catalog-stale', result.stdout)

    def test_catalog_audience_and_type(self):
        write(self.repo / 'docs/ai/README.md', '# AI 작업 안내\n')
        write(self.repo / 'docs/human/reference/api.md', '# API\n')
        self.check('--write-catalog')
        documents = {d['path']: d for d in json.loads((self.repo / 'catalog.json').read_text(encoding='utf-8'))['documents']}
        self.assertEqual(documents['docs/ai/README.md']['audience'], 'ai')
        self.assertEqual(documents['docs/human/reference/api.md']['type'], 'reference')

    def test_missing_image_and_anchor_fail(self):
        write(self.repo / 'docs/human/page.md', '# 화면\n\n<img src="missing.png" alt="화면"/>\n[이동](../../README.md#없는-제목)\n')
        result = self.check('--write-catalog')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing-link', result.stdout)
        self.assertIn('missing-anchor', result.stdout)

    def test_dash_rule_excludes_code_literal(self):
        path = self.repo / 'docs/human/page.md'
        write(path, '# 안내\n\n설명 — 부연\n')
        self.assertIn('aside-dash', self.check('--write-catalog').stdout)
        write(path, '# 안내\n\n로그는 `티어 정산 — 경기`입니다.\n')
        result = self.check('--write-catalog')
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_dash_rule_off_for_english(self):
        config = json.loads((self.repo / 'docs.config.json').read_text(encoding='utf-8'))
        config['project']['language'] = 'en'
        write(self.repo / 'docs.config.json', json.dumps(config))
        write(self.repo / 'docs/human/page.md', '# Guide\n\nText — aside\n')
        self.assertEqual(self.check('--write-catalog').returncode, 0)

    def test_source_must_exist(self):
        path = self.repo / 'docs/ai/sources.json'
        write(path, json.dumps({'sources': [{'id': 'start', 'repository': 'app', 'path': 'docs/human/missing.md'}]}))
        result = self.check('--write-catalog')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing-source', result.stdout)


class HubLayout(unittest.TestCase):
    """Documentation hub with one sibling code repository."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        workspace = Path(self.temp.name)
        self.doc = workspace / 'doc'
        self.api = workspace / 'api'
        (self.doc / 'scripts').mkdir(parents=True)
        shutil.copy(check_docs.__file__, str(self.doc / 'scripts' / 'check_docs.py'))
        write(self.doc / 'docs.config.json', json.dumps({
            'schema_version': 1, 'layout': 'hub', 'home': 'doc', 'project': {'name': 'Hub', 'language': 'ko'},
            'repositories': {
                'doc': {'local': 'doc', 'url': 'https://github.com/example/docs', 'branch': 'main'},
                'api': {'local': 'api', 'url': 'https://github.com/example/api', 'branch': 'dev'}}}))
        write(self.doc / 'README.md', '# 문서\n\n[API 안내](https://github.com/example/api/blob/dev/docs/human/README.md)\n')
        write(self.doc / 'human/README.md', '# 사람용 문서\n')
        write(self.api / 'README.md', '# API\n\n[문서](docs/human/README.md)\n')
        write(self.api / 'docs/human/README.md', '# API 문서\n')

    def tearDown(self):
        self.temp.cleanup()

    def check(self, *args):
        return subprocess.run([sys.executable, str(self.doc / 'scripts' / 'check_docs.py')] + list(args),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

    def test_workspace_checks_sibling_and_github_links(self):
        result = self.check('--write-catalog', '--workspace')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Checked 4 Markdown files', result.stdout)
        (self.api / 'docs/human/README.md').unlink()
        result = self.check('--workspace')
        self.assertIn('missing-link', result.stdout)

    def test_missing_sibling_repository(self):
        shutil.rmtree(str(self.api))
        result = self.check('--write-catalog', '--workspace')
        self.assertIn('Missing sibling repository', result.stdout)

    def test_repository_root_override(self):
        moved = Path(self.temp.name) / 'elsewhere'
        shutil.move(str(self.api), str(moved))
        env = dict(os.environ, DOCS_API_ROOT=str(moved))
        result = subprocess.run([sys.executable, str(self.doc / 'scripts' / 'check_docs.py'), '--write-catalog', '--workspace'],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, env=env)
        self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == '__main__':
    unittest.main()
