"""Scaffold and vendor behavior: idempotent output, marker sections, edited-file protection."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / 'scripts'))
import scaffold  # noqa: E402
import vendor  # noqa: E402


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def run(module, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = module.main(list(args))
    return code, out.getvalue()


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob('*')) if p.is_file()}


def single_config(root, **extra):
    config = {'schema_version': 1, 'layout': 'single', 'project': {'name': '샘플 앱', 'language': 'ko'},
              'repositories': {'app': {'local': '.', 'url': 'https://github.com/example/app', 'branch': 'main'}}}
    config.update(extra)
    write(root / 'docs.config.json', json.dumps(config, ensure_ascii=False))


class Scaffold(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'app'
        self.root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_second_run_changes_nothing(self):
        single_config(self.root)
        run(scaffold, '--root', str(self.root))
        before = snapshot(self.root)
        code, out = run(scaffold, '--root', str(self.root))
        self.assertEqual(code, 0)
        self.assertIn('Changed 0 files', out)
        self.assertEqual(before, snapshot(self.root))

    def test_existing_files_are_kept(self):
        single_config(self.root)
        write(self.root / 'docs/human/README.md', '# 기존 문서\n')
        write(self.root / 'AGENTS.md', '# 기존 규칙\n\n팀 규칙입니다.\n')
        run(scaffold, '--root', str(self.root))
        self.assertEqual((self.root / 'docs/human/README.md').read_text(encoding='utf-8'), '# 기존 문서\n')
        agents = (self.root / 'AGENTS.md').read_text(encoding='utf-8')
        self.assertTrue(agents.startswith('# 기존 규칙\n\n팀 규칙입니다.\n'))
        self.assertIn('<!-- devdog-docs:begin docs-update -->', agents)

    def test_marker_section_is_refreshed_in_place(self):
        single_config(self.root)
        run(scaffold, '--root', str(self.root))
        path = self.root / 'AGENTS.md'
        text = path.read_text(encoding='utf-8')
        edited = text.replace('## 장애 기록', '## 오래된 제목') + '\n팀 추가 규칙입니다.\n'
        write(path, edited)
        run(scaffold, '--root', str(self.root))
        text = path.read_text(encoding='utf-8')
        self.assertIn('## 장애 기록', text)
        self.assertNotIn('오래된 제목', text)
        self.assertIn('팀 추가 규칙입니다.', text)
        self.assertEqual(text.count('devdog-docs:begin incident'), 1)

    def test_selected_sections(self):
        single_config(self.root, agents={'sections': ['docs-update', 'branch-name']})
        run(scaffold, '--root', str(self.root))
        agents = (self.root / 'AGENTS.md').read_text(encoding='utf-8')
        self.assertIn('## 브랜치 이름', agents)
        self.assertNotIn('## 문서 위치', agents)

    def test_hub_creates_code_repository_documents(self):
        workspace = Path(self.temp.name)
        for name in ['doc', 'api']:
            (workspace / name).mkdir(exist_ok=True)
        write(workspace / 'doc/docs.config.json', json.dumps({
            'schema_version': 1, 'layout': 'hub', 'home': 'doc', 'project': {'name': '허브'},
            'repositories': {
                'doc': {'local': 'doc', 'url': 'https://github.com/example/docs', 'branch': 'main'},
                'api': {'local': 'api', 'url': 'https://github.com/example/api', 'branch': 'dev'},
                'web': {'local': 'web', 'url': 'https://github.com/example/web', 'branch': 'dev'}}}))
        code, out = run(scaffold, '--root', str(workspace / 'doc'))
        self.assertEqual(code, 0)
        self.assertIn('missing   web', out)
        self.assertTrue((workspace / 'doc/human/how-to/write-docs.md').exists())
        self.assertTrue((workspace / 'api/docs/human/how-to/README.md').exists())
        agents = (workspace / 'api/AGENTS.md').read_text(encoding='utf-8')
        self.assertIn('`../doc/human/how-to/write-docs.md`', agents)
        self.assertIn('https://github.com/example/docs/blob/main/human/how-to/write-docs.md', agents)
        tools = PLUGIN / 'templates' / 'tools' / 'check_docs.py'
        result = subprocess.run([sys.executable, str(tools), '--root', str(workspace / 'doc'), '--write-catalog', '--workspace'],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertIn('Missing sibling repository', result.stdout)
        self.assertIn('; 1 errors.', result.stdout)


class VendorTools(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'app'
        self.root.mkdir()
        single_config(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_copy_lock_and_protect_edits(self):
        code, out = run(vendor, 'tools', '--root', str(self.root))
        self.assertEqual(code, 0)
        lock = json.loads((self.root / '.devdog-docs.json').read_text(encoding='utf-8'))
        self.assertIn('scripts/check_docs.py', lock['files'])
        workflow = (self.root / '.github/workflows/docs-check.yml').read_text(encoding='utf-8')
        self.assertIn("'docs/ai/**'", workflow)
        self.assertIn('branches: [main]', workflow)
        _, out = run(vendor, 'tools', '--root', str(self.root))
        self.assertIn('unchanged scripts/check_docs.py', out)
        tool = self.root / 'scripts/check_docs.py'
        write(tool, tool.read_text(encoding='utf-8') + '\n# 프로젝트 수정\n')
        lock['files']['.github/workflows/docs-check.yml'] = 'old-hash'
        write(self.root / '.devdog-docs.json', json.dumps(lock))
        _, out = run(vendor, 'tools', '--root', str(self.root))
        self.assertIn('modified  scripts/check_docs.py', out)
        self.assertIn('# 프로젝트 수정', tool.read_text(encoding='utf-8'))
        _, out = run(vendor, 'tools', '--root', str(self.root), '--force')
        self.assertIn('updated   scripts/check_docs.py', out)
        self.assertNotIn('# 프로젝트 수정', tool.read_text(encoding='utf-8'))

    def test_upgrade_replaces_untouched_file(self):
        run(vendor, 'tools', '--root', str(self.root))
        tool = self.root / 'scripts/check_docs.py'
        old = b'# older release\n'
        tool.write_bytes(old)
        lock_path = self.root / '.devdog-docs.json'
        lock = json.loads(lock_path.read_text(encoding='utf-8'))
        lock['files']['scripts/check_docs.py'] = vendor.digest(old)
        write(lock_path, json.dumps(lock))
        _, out = run(vendor, 'tools', '--root', str(self.root))
        self.assertIn('updated   scripts/check_docs.py', out)
        self.assertNotEqual(tool.read_bytes(), old)


if __name__ == '__main__':
    unittest.main()
