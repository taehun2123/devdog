"""Migration: inventory draft, git moves, link rewriting, migration map."""
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
import apply_moves  # noqa: E402
import inventory  # noqa: E402

TOOLS = PLUGIN / 'templates' / 'tools' / 'check_docs.py'


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


class Classify(unittest.TestCase):
    def test_token_boundaries(self):
        self.assertEqual(inventory.classify('docs/OLD_API.md', '')[0], 'archive')
        self.assertEqual(inventory.classify('docs/folder.md', '폴더 구조')[0], 'explanation')
        self.assertEqual(inventory.classify('docs/rapid.md', '')[0], 'explanation')
        self.assertEqual(inventory.classify('docs/CODE_COMMENT_CONVENTION.md', '')[0], 'reference')
        self.assertEqual(inventory.classify('docs/DEPLOY.md', '')[0], 'how-to')
        self.assertEqual(inventory.classify('docs/2026-09-13 회의.md', '')[0], 'archive')
        self.assertEqual(inventory.classify('prompts/screen.md', '')[:2], ('ai', 'ai'))

    def test_kebab_names(self):
        self.assertEqual(inventory.kebab('CODE_COMMENT_CONVENTION'), 'code-comment-convention')
        self.assertEqual(inventory.kebab('gameInviteLinks'), 'game-invite-links')
        self.assertEqual(inventory.kebab('배포 절차'), '배포-절차')


class Migrate(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'app'
        self.root.mkdir()
        git(self.root, 'init', '-q')
        git(self.root, 'config', 'user.email', 't@example.com')
        git(self.root, 'config', 'user.name', 'test')
        write(self.root / 'docs.config.json', json.dumps({
            'schema_version': 1, 'layout': 'single', 'project': {'name': '앱', 'language': 'ko'},
            'repositories': {'app': {'local': '.', 'url': 'https://github.com/example/app', 'branch': 'main'}}}))
        write(self.root / 'README.md', '# 앱\n\n[배포](docs/DEPLOY.md#순서) · [API](docs/API.md)\n'
                                        '[원격](https://github.com/example/app/blob/main/docs/API.md)\n')
        write(self.root / 'docs/DEPLOY.md', '# 배포 절차\n\n## 순서\n\n[API 설명](API.md) ![구성](img/flow.png)\n'
                                             '[앱 소개](../README.md)\n\n```text\n[예시](API.md)\n```\n')
        write(self.root / 'docs/API.md', '# API\n\n[배포 문서](./DEPLOY.md) [참고]: <회의 기록.md>\n\n[참고]: <회의 기록.md>\n')
        write(self.root / 'docs/회의 기록.md', '# 2026-09-01 회의\n\n[API](API.md)\n')
        write(self.root / 'docs/img/flow.png', 'png')
        write(self.root / 'server/README.md', '# 서버 폴더\n\n[배포](../docs/DEPLOY.md)\n')
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-qm', 'init')

    def tearDown(self):
        self.temp.cleanup()

    def plan(self):
        code, out = run(inventory, '--root', str(self.root))
        self.assertEqual(code, 0, out)
        return json.loads((self.root / 'docs-migration-plan.json').read_text(encoding='utf-8'))

    def test_inventory_plan(self):
        plan = self.plan()
        moves = {m['from']: m['to'] for m in plan['moves']}
        self.assertEqual(moves['docs/DEPLOY.md'], 'docs/human/how-to/deploy.md')
        self.assertEqual(moves['docs/API.md'], 'docs/human/reference/api.md')
        self.assertEqual(moves['docs/회의 기록.md'], 'docs/human/archive/회의-기록.md')
        kept = {k['path'] for k in plan['keep']}
        self.assertIn('README.md', kept)
        self.assertIn('server/README.md', kept)

    def test_apply_moves_and_links(self):
        plan = self.plan()
        plan_path = self.root / 'docs-migration-plan.json'
        code, out = run(apply_moves, str(plan_path), '--root', str(self.root))
        self.assertEqual(code, 0, out)
        readme = (self.root / 'README.md').read_text(encoding='utf-8')
        self.assertIn('[배포](docs/human/how-to/deploy.md#순서)', readme)
        self.assertIn('https://github.com/example/app/blob/main/docs/human/reference/api.md', readme)
        deploy = (self.root / 'docs/human/how-to/deploy.md').read_text(encoding='utf-8')
        self.assertIn('[API 설명](../reference/api.md)', deploy)
        self.assertIn('![구성](../../img/flow.png)', deploy)
        self.assertIn('[앱 소개](../../../README.md)', deploy)
        self.assertIn('[예시](API.md)', deploy, 'code block must stay untouched')
        api = (self.root / 'docs/human/reference/api.md').read_text(encoding='utf-8')
        self.assertIn('[배포 문서](../how-to/deploy.md)', api)
        self.assertIn('[참고]: <../archive/회의-기록.md>', api)
        server = (self.root / 'server/README.md').read_text(encoding='utf-8')
        self.assertIn('[배포](../docs/human/how-to/deploy.md)', server)
        status = subprocess.run(['git', '-C', str(self.root), 'status', '--porcelain'], stdout=subprocess.PIPE,
                                encoding='utf-8', errors='replace').stdout
        self.assertRegex(status, r'R. docs/DEPLOY.md -> docs/human/how-to/deploy.md')
        mapping = json.loads((self.root / 'migration-map.json').read_text(encoding='utf-8'))
        self.assertIn({'repository': 'app', 'from': 'docs/API.md', 'to': 'docs/human/reference/api.md'}, mapping['moves'])
        result = subprocess.run([sys.executable, str(TOOLS), '--root', str(self.root), '--write-catalog'],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8', errors='replace')
        self.assertNotIn('missing-link', result.stdout)
        self.assertNotIn('missing-anchor', result.stdout)

    def test_invalid_plan_is_rejected(self):
        plan = self.plan()
        plan['moves'][0]['to'] = '../outside.md'
        path = self.root / 'bad-plan.json'
        write(path, json.dumps(plan))
        code, out = run(apply_moves, str(path), '--root', str(self.root))
        self.assertEqual(code, 1)
        self.assertIn('target outside repository', out)
        self.assertTrue((self.root / 'docs/API.md').exists())

    def test_outside_link_follows_moved_file(self):
        write(self.root / 'docs/LINKS.md', '# 링크\n\n[다른 저장소](../../other/README.md)\n')
        plan = {'schema_version': 1, 'repository': 'app',
                'moves': [{'from': 'docs/LINKS.md', 'to': 'docs/human/reference/links.md'}], 'keep': []}
        path = self.root / 'plan.json'
        write(path, json.dumps(plan))
        run(apply_moves, str(path), '--root', str(self.root))
        text = (self.root / 'docs/human/reference/links.md').read_text(encoding='utf-8')
        self.assertIn('[다른 저장소](../../../../other/README.md)', text)


if __name__ == '__main__':
    unittest.main()
