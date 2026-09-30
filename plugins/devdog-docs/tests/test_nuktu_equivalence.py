"""Compare the generalized tools with the NUKTU workspace they were extracted from.

Runs only when DEVDOG_DOCS_NUKTU points at the NUKTU workspace (doc, backend,
frontend, marketing). Nothing in that workspace is modified except the ignored
doc/.site build folder when DEVDOG_DOCS_NODE_MODULES is also set.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
CONFIG = PLUGIN / 'tests' / 'fixtures' / 'nuktu.config.json'
WORKSPACE = os.environ.get('DEVDOG_DOCS_NUKTU')
NODE_MODULES = os.environ.get('DEVDOG_DOCS_NODE_MODULES')


def last_line(args, cwd):
    result = subprocess.run(args, cwd=str(cwd), stdout=subprocess.PIPE, universal_newlines=True)
    return result.stdout.strip().splitlines()[-1]


@unittest.skipUnless(WORKSPACE, 'Set DEVDOG_DOCS_NUKTU to the NUKTU workspace')
class NuktuEquivalence(unittest.TestCase):
    def test_checker_output(self):
        doc = Path(WORKSPACE) / 'doc'
        tool = PLUGIN / 'templates' / 'tools' / 'check_docs.py'
        for extra in ([], ['--workspace']):
            original = last_line([sys.executable, 'scripts/check_docs.py'] + extra, doc)
            general = last_line([sys.executable, str(tool), '--root', str(doc), '--config', str(CONFIG)] + extra, doc)
            self.assertEqual(original, general)

    @unittest.skipUnless(NODE_MODULES and shutil.which('node'), 'Set DEVDOG_DOCS_NODE_MODULES to compare site manifests')
    def test_site_manifest(self):
        doc = Path(WORKSPACE) / 'doc'
        subprocess.run(['node', 'scripts/site/prepare.mjs'], cwd=str(doc), check=True, stdout=subprocess.PIPE)
        with tempfile.TemporaryDirectory() as temp:
            site = Path(temp) / 'site'
            shutil.copytree(str(PLUGIN / 'templates' / 'site'), str(site))
            os.symlink(NODE_MODULES, str(site / 'node_modules'))
            env = dict(os.environ, DOCS_CONFIG=str(CONFIG), DOCS_DOC_ROOT=str(doc), DOCS_WORKSPACE=WORKSPACE)
            subprocess.run(['node', 'scripts/site/prepare.mjs'], cwd=str(site), check=True, env=env, stdout=subprocess.PIPE)
            general = json.loads((site / '.site' / 'manifest.json').read_text(encoding='utf-8'))
        original = json.loads((doc / '.site' / 'manifest.json').read_text(encoding='utf-8'))
        key = lambda e: (e['repository'], e['path'], e['route'], e['kind'], e['archive'], e.get('title'))  # noqa: E731
        self.assertEqual(sorted(map(key, original['entries'])), sorted(map(key, general['entries'])))
        self.assertEqual(original['aliases'], general['aliases'])


if __name__ == '__main__':
    unittest.main()
