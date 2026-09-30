#!/usr/bin/env python3
"""Create the devdog-docs folder layout from docs.config.json.

Existing files are never overwritten. AGENTS.md sections between
devdog-docs markers are inserted or refreshed. Running twice changes nothing.
"""
import argparse
import json
import re
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
TEMPLATES = PLUGIN / 'templates'
sys.path.insert(0, str(TEMPLATES / 'tools'))
from check_docs import load_config  # noqa: E402

DEFAULT_SECTIONS = ['docs-layout', 'docs-update', 'incident']
KIND_FOLDERS = ['tutorials', 'how-to', 'explanation', 'reference']
EMPTY_LIST = '아직 등록된 문서가 없습니다. 문서를 추가하면 이 목록에 링크를 추가하십시오.'
HOME_ITEMS = {
    'how-to': '- [문서 작성 안내](write-docs.md)',
    'explanation': '- [장애 조사 기록](troubleshooting/README.md)',
    'reference': '- [원본 문서 위치](document-locations.md)',
}


def render(text, values):
    def replace(match):
        key = match.group(1)
        if key not in values:
            raise KeyError('Unknown template value: %s' % key)
        return values[key]
    return re.sub(r'\{\{(\w+)\}\}', replace, text)


def read_template(rel):
    return (TEMPLATES / rel).read_text(encoding='utf-8')


class Writer(object):
    def __init__(self, dry_run):
        self.dry_run = dry_run
        self.results = []

    def log(self, state, path):
        self.results.append((state, path))

    def write_new(self, path, text):
        if path.exists():
            self.log('exists', path); return
        if not self.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
        self.log('created', path)

    def write_sections(self, path, title, sections):
        """Insert or refresh marked sections. Text outside the markers stays as is."""
        existed = path.exists()
        original = path.read_text(encoding='utf-8') if existed else '# %s\n' % title
        text = original
        for name, body in sections:
            begin, end = '<!-- devdog-docs:begin %s -->' % name, '<!-- devdog-docs:end %s -->' % name
            block = '%s\n%s\n%s' % (begin, body.strip('\n'), end)
            pattern = re.compile(re.escape(begin) + r'.*?' + re.escape(end), re.S)
            if pattern.search(text):
                text = pattern.sub(lambda _: block, text)
            else:
                text = text.rstrip('\n') + '\n\n' + block + '\n'
        if text == original and existed:
            self.log('unchanged', path); return
        if not self.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
        self.log('updated' if existed else 'created', path)


def kind_readme(kind, items):
    return render(read_template('docs/human/%s/README.md' % kind), {'items': items})


def home_documents(config, writer, project):
    repos = config['repos']
    home = repos[config['home']]
    root, human, ai = home['root'], home['human'], home['ai']
    values = {'human': human, 'ai': ai, 'project': project}
    for kind in KIND_FOLDERS:
        writer.write_new(root / human / kind / 'README.md', kind_readme(kind, HOME_ITEMS.get(kind, EMPTY_LIST)))
    others = [r for r in repos.values() if not r['home']]
    rows = ''.join('| %s 문서 | `%s/%s/` | %s |\n' % (r['name'], r['local'], r['human'], r['name']) for r in others)
    links = ''
    if others:
        links = '\n## 저장소별 문서\n\n' + ''.join(
            '- [%s 문서](%s)\n' % (r['name'], github(r, r['human'] + '/README.md')) for r in others)
    fixed = {
        'human/README.md': read_template('docs/human/README.md'),
        'human/how-to/write-docs.md': render(read_template('docs/human/how-to/write-docs.md'), values),
        'human/reference/document-locations.md': render(read_template('docs/human/reference/document-locations.md'),
                                                        dict(values, repository_rows=rows, repository_links=links)),
        'human/archive/README.md': read_template('docs/human/archive/README.md'),
        'human/explanation/troubleshooting/README.md': read_template('docs/human/explanation/troubleshooting/README.md'),
    }
    for rel, text in fixed.items():
        writer.write_new(root / human / rel[len('human/'):], text)
    writer.write_new(root / ai / 'README.md', read_template('docs/ai/README.md'))
    sources = {'schema_version': 1, 'sources': [{
        'id': 'docs-process', 'repository': config['home'], 'path': human + '/how-to/write-docs.md',
        'purpose': '문서 작성·검증', 'kind': 'policy'}]}
    writer.write_new(root / ai / 'sources.json', json.dumps(sources, ensure_ascii=False, indent=2) + '\n')
    if config['layout'] == 'hub':
        tree = [home['local'] + '/', '├── README.md          전체 문서 안내',
                '├── %-18s 사람이 읽는 설명과 공통 규칙' % (human + '/'),
                '├── %-18s AI 작업 안내와 참고할 파일 목록' % (ai + '/'),
                '└── docs.config.json   저장소·사이트 설정']
        for repo in others:
            tree.append('%-22s AGENTS.md + %s + %s' % (repo['local'] + '/', repo['human'], repo['ai']))
        writer.write_new(root / 'README.md', render(read_template('docs/hub-README.md'),
                                                    {'project': project, 'tree': '\n'.join(tree)}))


def github(repo, rel):
    if repo['url']:
        return '%s/blob/%s/%s' % (repo['url'], repo['branch'], rel)
    return '../' + repo['local'] + '/' + rel


def repo_values(config, repo):
    home = config['repos'][config['home']]
    if repo['home']:
        check = '`python3 scripts/check_docs.py --write-catalog`와 `python3 scripts/check_docs.py`를 실행하십시오.'
        if config['layout'] == 'hub':
            check += ' 형제 저장소가 있으면 `python3 scripts/check_docs.py --workspace`도 실행하십시오.'
        return {
            'human': repo['human'], 'ai': repo['ai'],
            'write_docs': '[문서 작성 안내](%s/how-to/write-docs.md)' % repo['human'],
            'write_docs_fallback': '',
            'check': check,
            'troubleshooting': '`%s/explanation/troubleshooting/`' % repo['human'],
        }
    hub_path = '../%s/%s' % (home['local'], home['human'])
    fallback = ''
    if home['url']:
        fallback = ' 형제 문서 저장소가 없을 때의 기준은 [문서 작성 안내](%s)입니다.' % github(home, home['human'] + '/how-to/write-docs.md')
    return {
        'human': repo['human'], 'ai': repo['ai'],
        'write_docs': '`%s/how-to/write-docs.md`' % hub_path,
        'write_docs_fallback': fallback,
        'check': '문서 저장소(`../%s`)에서 `python3 scripts/check_docs.py --workspace`를 실행하십시오.' % home['local'],
        'troubleshooting': '`%s/explanation/troubleshooting/`' % hub_path,
    }


def code_repo_documents(config, repo, writer):
    home = config['repos'][config['home']]
    root = repo['root']
    human_readme = render(read_template('repo/human/README.md'), {
        'repo': repo['name'], 'hub_readme': github(home, 'README.md')})
    writer.write_new(root / repo['human'] / 'README.md', human_readme)
    for kind in KIND_FOLDERS:
        writer.write_new(root / repo['human'] / kind / 'README.md', kind_readme(kind, EMPTY_LIST))
    writer.write_new(root / repo['ai'] / 'README.md', render(read_template('repo/ai/README.md'), {
        'hub_write_docs': github(home, home['human'] + '/how-to/write-docs.md')}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--root', default='.', help='Repository that owns docs.config.json.')
    parser.add_argument('--config', help='Default: <root>/docs.config.json')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    config_path = Path(args.config).resolve() if args.config else root / 'docs.config.json'
    raw = json.loads(config_path.read_text(encoding='utf-8'))
    config = load_config(root, config_path)
    project = raw.get('project', {}).get('name', root.name)
    sections = raw.get('agents', {}).get('sections', DEFAULT_SECTIONS)
    writer = Writer(args.dry_run)
    home_documents(config, writer, project)
    missing = []
    for repo in config['repos'].values():
        if not repo['root'].is_dir():
            missing.append(repo['name']); continue
        if not repo['home']:
            code_repo_documents(config, repo, writer)
        values = repo_values(config, repo)
        bodies = [(name, render(read_template('agents/%s.md' % name), values)) for name in sections]
        writer.write_sections(repo['root'] / 'AGENTS.md', '%s 작업 규칙' % repo['name'], bodies)
        writer.write_new(repo['root'] / 'CLAUDE.md', '@AGENTS.md\n')
    for state, path in writer.results:
        print('%-9s %s' % (state, path))
    for name in missing:
        print('missing   %s (repository folder not found; skipped)' % name)
    changed = sum(1 for state, _ in writer.results if state in ('created', 'updated'))
    print('%s %d files%s.' % ('Would change' if args.dry_run else 'Changed', changed,
                             '' if not missing else ', %d repositories skipped' % len(missing)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
