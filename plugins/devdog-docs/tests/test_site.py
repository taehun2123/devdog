"""Site vendoring and generated workflows. The full build runs only with DEVDOG_DOCS_E2E=1."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / 'scripts'))
sys.path.insert(0, str(PLUGIN / 'templates' / 'tools'))
import apply_moves  # noqa: E402
import inventory  # noqa: E402
import scaffold  # noqa: E402
import site_workflows  # noqa: E402
import vendor  # noqa: E402
from check_docs import load_config  # noqa: E402

E2E = os.environ.get('DEVDOG_DOCS_E2E') == '1'
NODE_MODULES = os.environ.get('DEVDOG_DOCS_NODE_MODULES')


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def run(module, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = module.main(list(args))
    return code, out.getvalue()


def git(root, *args):
    subprocess.run(['git', '-C', str(root)] + list(args), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def init_repo(root):
    root.mkdir(parents=True, exist_ok=True)
    git(root, 'init', '-q')
    git(root, 'config', 'user.email', 't@example.com')
    git(root, 'config', 'user.name', 'test')


def commit(root):
    git(root, 'add', '-A')
    git(root, 'commit', '-qm', 'update', '--allow-empty')


SINGLE = {'schema_version': 1, 'layout': 'single', 'project': {'name': '샘플 앱', 'language': 'ko'},
          'repositories': {'app': {'local': '.', 'url': 'https://github.com/example/app', 'branch': 'main', 'mount': 'guide'}},
          'site': {'base': '/app/', 'searchQuery': '배포'}}
HUB = {'schema_version': 1, 'layout': 'hub', 'home': 'doc', 'project': {'name': '샘플 팀', 'language': 'ko'},
       'repositories': {
           'doc': {'local': 'doc', 'url': 'https://github.com/example/docs', 'branch': 'main', 'mount': 'guide'},
           'api': {'local': 'api', 'url': 'https://github.com/example/api', 'branch': 'dev', 'label': 'API 서버'}},
       'site': {'base': '/docs/', 'searchQuery': '배포'}}


class Workflows(unittest.TestCase):
    def config(self, raw, root):
        path = root / 'docs.config.json'
        write(path, json.dumps(raw, ensure_ascii=False))
        return load_config(root, path)

    def test_single_pages_workflow(self):
        with tempfile.TemporaryDirectory() as temp:
            config = self.config(SINGLE, Path(temp))
            text = site_workflows.pages(config, SINGLE)
        self.assertIn('branches: [main]', text)
        self.assertIn('node-version-file: docs-site/.nvmrc', text)
        self.assertIn('run: python3 scripts/check_docs.py\n', text)
        self.assertIn('path: docs-site/.site/dist', text)
        self.assertNotIn('schedule:', text)
        self.assertIn('uses: actions/deploy-pages@v4', text)

    def test_hub_pages_and_notify_workflows(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'doc'
            config = self.config(HUB, root)
            text = site_workflows.pages(config, HUB)
            notify = site_workflows.notify(config, config['repos']['api'])
        self.assertIn('repository: example/api', text)
        self.assertIn('path: api', text)
        self.assertIn('run: python3 scripts/check_docs.py --workspace', text)
        self.assertIn('working-directory: doc', text)
        self.assertIn("cron: '17 * * * *'", text)
        self.assertIn('repos/example/docs/dispatches', notify)
        self.assertIn("paths: ['docs/human/**', 'README.md']", notify)

    def test_repository_url_is_required_for_checkout(self):
        raw = json.loads(json.dumps(HUB))
        raw['repositories']['api']['url'] = 'https://gitlab.com/group/sub/api'
        with tempfile.TemporaryDirectory() as temp:
            config = self.config(raw, Path(temp) / 'doc')
            with self.assertRaises(ValueError):
                site_workflows.pages(config, raw)

    def test_home_page_values(self):
        with tempfile.TemporaryDirectory() as temp:
            config = self.config(HUB, Path(temp) / 'doc')
            values = site_workflows.home_page(config, HUB)
        self.assertEqual(values['title'], '"샘플 팀 문서"')
        self.assertIn('title: "API 서버"', values['features'])
        self.assertIn('link: /api/index.html', values['features'])


class VendorSite(unittest.TestCase):
    def test_single_site_folder_seeds_and_gitignore(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'app'
            write(root / 'docs.config.json', json.dumps(SINGLE, ensure_ascii=False))
            write(root / '.gitignore', 'dist/\n')
            code, out = run(vendor, 'site', '--root', str(root))
            self.assertEqual(code, 0, out)
            self.assertTrue((root / 'docs-site/package.json').exists())
            self.assertTrue((root / 'docs-site/scripts/site/prepare.mjs').exists())
            self.assertFalse((root / 'package.json').exists())
            home = (root / 'docs-site/site/home.md').read_text(encoding='utf-8')
            self.assertIn('name: "샘플 앱 문서"', home)
            self.assertIn('link: /guide/index.html', home)
            ignore = (root / '.gitignore').read_text(encoding='utf-8')
            self.assertIn('docs-site/node_modules\n', ignore)
            write(root / 'docs-site/site/home.md', '---\nlayout: home\n---\n')
            _, out = run(vendor, 'site', '--root', str(root))
            self.assertIn('kept      docs-site/site/home.md', out)
            self.assertNotIn('ignored', out)
            self.assertEqual((root / '.gitignore').read_text(encoding='utf-8'), ignore)
            lock = json.loads((root / '.devdog-docs.json').read_text(encoding='utf-8'))
            self.assertNotIn('docs-site/site/home.md', lock['files'])
            self.assertIn('docs-site/scripts/site/prepare.mjs', lock['files'])


def npm_install(site):
    if NODE_MODULES:
        os.symlink(NODE_MODULES, str(site / 'node_modules'))
        return
    subprocess.run(['npm', 'ci', '--no-audit', '--no-fund'], cwd=str(site), check=True)


def npm(site, *args, env=None):
    result = subprocess.run(['npm', 'run'] + list(args), cwd=str(site), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            encoding='utf-8', errors='replace', env=dict(os.environ, **(env or {})))
    return result.returncode, result.stdout


@unittest.skipUnless(E2E and shutil.which('npm'), 'Set DEVDOG_DOCS_E2E=1 with Node.js 22 to build the site')
class EndToEnd(unittest.TestCase):
    def test_single_repository(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'app'
            init_repo(root)
            write(root / 'README.md', '# 샘플 앱\n\n[배포 안내](docs/DEPLOY.md)\n')
            write(root / 'docs/DEPLOY.md', '# 배포 절차\n\n배포 순서입니다.\n\n```mermaid\nflowchart LR\n  A --> B\n```\n\n[API](API.md)\n')
            write(root / 'docs/API.md', '# API 명세\n\n## 로그인\n')
            write(root / 'docs/2025-01-02-meeting.md', '# 2025-01-02 회의\n\n지난 회의입니다.\n')
            write(root / 'docs.config.json', json.dumps(SINGLE, ensure_ascii=False))
            commit(root)
            self.assertEqual(run(scaffold, '--root', str(root))[0], 0)
            self.assertEqual(run(vendor, 'tools', '--root', str(root))[0], 0)
            run(inventory, '--root', str(root))
            self.assertEqual(run(apply_moves, str(root / 'docs-migration-plan.json'), '--root', str(root))[0], 0)
            (root / 'docs-migration-plan.json').unlink()
            self.assertEqual(run(vendor, 'site', '--root', str(root))[0], 0)
            check = subprocess.run([sys.executable, str(root / 'scripts/check_docs.py'), '--write-catalog'],
                                   stdout=subprocess.PIPE, encoding='utf-8', errors='replace')
            self.assertIn('0 errors', check.stdout)
            commit(root)
            site = root / 'docs-site'
            npm_install(site)
            code, out = npm(site, 'test')
            self.assertEqual(code, 0, out)
            code, out = npm(site, 'docs:build', env={'DOCS_REQUIRE_CLEAN': '1'})
            self.assertEqual(code, 0, out)
            self.assertIn('Verified', out)
            page = (site / '.site/dist/guide/reference/api.html').read_text(encoding='utf-8')
            self.assertIn('/app/', page)

    def test_documentation_hub(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            for name in ['doc', 'api']:
                init_repo(workspace / name)
            write(workspace / 'api/README.md', '# API 서버\n\n[배포](docs/DEPLOY.md)\n')
            write(workspace / 'api/docs/DEPLOY.md', '# 배포 절차\n\n배포 순서입니다.\n')
            write(workspace / 'doc/docs.config.json', json.dumps(HUB, ensure_ascii=False))
            for name in ['doc', 'api']:
                commit(workspace / name)
            home = workspace / 'doc'
            run(scaffold, '--root', str(home))
            run(vendor, 'tools', '--root', str(home))
            run(inventory, '--root', str(home), '--repository', 'api')
            self.assertEqual(run(apply_moves, str(workspace / 'api/docs-migration-plan.json'), '--root', str(home))[0], 0)
            (workspace / 'api/docs-migration-plan.json').unlink()
            run(vendor, 'site', '--root', str(home))
            self.assertTrue((workspace / 'api/.github/workflows/notify-docs.yml').exists())
            check = subprocess.run([sys.executable, str(home / 'scripts/check_docs.py'), '--write-catalog', '--workspace'],
                                   stdout=subprocess.PIPE, encoding='utf-8', errors='replace')
            self.assertIn('0 errors', check.stdout)
            for name in ['doc', 'api']:
                commit(workspace / name)
            npm_install(home)
            code, out = npm(home, 'docs:build', env={'DOCS_REQUIRE_CLEAN': '1'})
            self.assertEqual(code, 0, out)
            self.assertTrue((home / '.site/dist/api/how-to/deploy.html').exists())


if __name__ == '__main__':
    unittest.main()
