#!/usr/bin/env python3
"""Copy devdog-docs tool files into a project and keep them upgradable.

The lock file .devdog-docs.json records the hash of every copied file.
A file whose current hash differs from the lock was edited in the project;
it is reported and left alone unless --force is given.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
TEMPLATES = PLUGIN / 'templates'
sys.path.insert(0, str(TEMPLATES / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_docs import load_config  # noqa: E402

LOCK = '.devdog-docs.json'
# Seed files are project content after the first copy. They are created once and never upgraded.
SEED = {'site/home.md'}


def version():
    return json.loads((PLUGIN / '.claude-plugin' / 'plugin.json').read_text(encoding='utf-8'))['version']


def digest(data):
    return hashlib.sha256(data).hexdigest()


def render(text, values):
    return re.sub(r'\{\{(\w+)\}\}', lambda m: values.get(m.group(1), m.group(0)), text)


def tool_files(config):
    home = config['repos'][config['home']]
    values = {'ai': home['ai'], 'branch': home['branch']}
    return [
        ('scripts/check_docs.py', (TEMPLATES / 'tools' / 'check_docs.py').read_bytes()),
        ('.github/workflows/docs-check.yml',
         render((TEMPLATES / 'workflows' / 'docs-check.yml').read_text(encoding='utf-8'), values).encode('utf-8')),
    ]


def site_files(config, raw):
    """Site tooling for the home repository. Workflows are generated from the config."""
    import site_workflows  # noqa: E402  (same folder)
    files = []
    base = TEMPLATES / 'site'
    for path in sorted(base.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and 'node_modules' not in path.parts:
            files.append((path.relative_to(base).as_posix(), path.read_bytes()))
    files.append(('.github/workflows/docs-pages.yml', site_workflows.pages(config, raw).encode('utf-8')))
    return files


class Vendor(object):
    def __init__(self, root, force, dry_run):
        self.root = root
        self.force = force
        self.dry_run = dry_run
        path = root / LOCK
        self.lock = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'files': {}}
        self.results = []

    def put(self, rel, data, seed=False):
        target = self.root / rel
        new = digest(data)
        if target.exists():
            current = digest(target.read_bytes())
            locked = self.lock['files'].get(rel)
            if current == new:
                state = 'unchanged'
            elif seed:
                state = 'kept'
            elif locked == current or self.force:
                state = 'updated'
            else:
                self.results.append(('modified', rel)); return
        else:
            state = 'created'
        if state in ('created', 'updated') and not self.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        if not seed:
            self.lock['files'][rel] = new
        self.results.append((state, rel))

    def save(self):
        if self.dry_run:
            return
        self.lock['version'] = version()
        self.lock['files'] = dict(sorted(self.lock['files'].items()))
        (self.root / LOCK).write_text(json.dumps(self.lock, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('target', choices=['tools', 'site'])
    parser.add_argument('--root', default='.')
    parser.add_argument('--config')
    parser.add_argument('--force', action='store_true', help='Overwrite files edited in the project.')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    config_path = Path(args.config).resolve() if args.config else root / 'docs.config.json'
    raw = json.loads(config_path.read_text(encoding='utf-8'))
    config = load_config(root, config_path)
    vendor = Vendor(root, args.force, args.dry_run)
    files = tool_files(config) if args.target == 'tools' else site_files(config, raw)
    for rel, data in files:
        vendor.put(rel, data, seed=rel in SEED)
    vendor.save()
    extra = []
    if args.target == 'site' and config['layout'] == 'hub':
        import site_workflows  # noqa: E402
        for repo in config['repos'].values():
            if repo['home'] or not repo['root'].is_dir():
                continue
            target = repo['root'] / '.github' / 'workflows' / 'notify-docs.yml'
            text = site_workflows.notify(config, repo)
            if target.exists():
                extra.append(('exists', target)); continue
            if not args.dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding='utf-8')
            extra.append(('created', target))
    for state, rel in vendor.results:
        print('%-9s %s' % (state, rel))
    for state, path in extra:
        print('%-9s %s' % (state, path))
    modified = [rel for state, rel in vendor.results if state == 'modified']
    if modified:
        print('Skipped %d files edited in this project. Review the differences, then rerun with --force to replace them.' % len(modified))
    return 0


if __name__ == '__main__':
    sys.exit(main())
