#!/usr/bin/env python3
"""Check documentation without third-party packages or network access.

Settings come from docs.config.json. The file layout follows the devdog-docs
plugin: human/ai separation, README/AGENTS/CLAUDE at each repository root.
"""
import argparse
import collections
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unicodedata
from urllib.parse import unquote, urlsplit

STYLE_RULES = {'heading-level', 'h1-count', 'fence-language', 'image-alt', 'aside-dash'}
KINDS = ['tutorials', 'how-to', 'explanation', 'reference', 'archive']
ROOT_FILES = ['README.md', 'AGENTS.md', 'CLAUDE.md']


def relative(path, base):
    """Path.relative_to without raising. Python 3.8 has no is_relative_to."""
    try:
        return path.relative_to(base)
    except ValueError:
        return None


def load_config(root, config_path):
    data = json.loads(config_path.read_text(encoding='utf-8'))
    layout = data.get('layout', 'single')
    specs = data['repositories']
    home = data.get('home') or next((k for k, v in specs.items() if v.get('local') in ('.', None)), next(iter(specs)))
    repos = {}
    for name, spec in specs.items():
        is_home = name == home
        default_human = 'human' if layout == 'hub' and is_home else 'docs/human'
        default_ai = 'ai' if layout == 'hub' and is_home else 'docs/ai'
        human = spec.get('human', default_human)
        ai = spec.get('ai', default_ai)
        override = os.environ.get('DOCS_%s_ROOT' % re.sub(r'\W', '_', name.upper()))
        if is_home:
            path = root
        elif override:
            path = Path(override).resolve()
        else:
            path = (root.parent / spec.get('local', name)).resolve()
        repos[name] = {
            'name': name,
            'root': path,
            'home': is_home,
            'local': spec.get('local', name),
            'branch': spec.get('branch', 'main'),
            'mount': spec.get('mount', name),
            'url': spec.get('url', '').rstrip('/'),
            'human': human,
            'ai': ai,
            'checkRoots': spec.get('checkRoots', [human, ai]),
            'extraDocuments': spec.get('extraDocuments', []),
            'skipOnConflict': spec.get('skipOnConflict', []),
        }
    language = data.get('project', {}).get('language', 'ko')
    rules = data.get('rules', {})
    return {
        'layout': layout,
        'home': home,
        'repos': repos,
        'asideDash': rules.get('asideDash', language == 'ko'),
        'compatibility': data.get('catalog', {}).get('compatibility', []),
    }


def documents(repo):
    root = repo['root']
    result = set()
    for name in ROOT_FILES:
        if (root / name).exists():
            result.add(root / name)
    for folder in repo['checkRoots']:
        if (root / folder).exists():
            result.update((root / folder).rglob('*.md'))
    for rel in repo['extraDocuments']:
        if (root / rel).exists():
            result.add(root / rel)
    return sorted(result)


def prose_lines(text):
    """Keep line numbers, omitting fenced and indented code examples."""
    fence = None
    for number, line in enumerate(text.splitlines(), 1):
        match = re.match(r'^\s{0,3}(`{3,}|~{3,})(.*)$', line)
        if match:
            marker, language = match.groups()
            if fence is None:
                fence = marker
                yield number, '', language.strip(), True
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
            continue
        if fence is None and not line.startswith(('    ', '\t')):
            yield number, line, None, False


def slug(text):
    text = re.sub(r'<[^>]*>', '', html.unescape(text)).lower().strip()
    text = text.replace('`', '').replace('*', '').replace('~', '')
    return ''.join(c for c in text if c in '-_ ' or unicodedata.category(c)[0] in 'LN').replace(' ', '-')


def anchors(path):
    found, counts = set(), collections.Counter()
    for _, line, _, _ in prose_lines(path.read_text(encoding='utf-8')):
        m = re.match(r'^#{1,6}\s+(.*?)\s*#*$', line)
        if m:
            base = slug(m.group(1)); n = counts[base]; counts[base] += 1
            found.add(base if n == 0 else '%s-%d' % (base, n))
        found.update(re.findall(r'(?:id|name)=["\']([^"\']+)', line))
    return found


def markdown_links(line):
    """Read inline links with nested parentheses, angle paths, and optional titles."""
    pattern = re.compile(r'(!?)\[([^\]\n]*)\]\(')
    for m in pattern.finditer(line):
        start = m.end(); pos = start
        if pos < len(line) and line[pos] == '<':
            end = line.find('>', pos)
            if end >= 0:
                yield m.group(1) == '!', m.group(2), line[pos + 1:end]
            continue
        depth = 0
        while pos < len(line):
            c = line[pos]
            if c == '\\':
                pos += 2; continue
            if c == '(':
                depth += 1
            elif c == ')':
                if depth == 0:
                    break
                depth -= 1
            elif c.isspace() and depth == 0:
                break
            pos += 1
        if pos > start:
            yield m.group(1) == '!', m.group(2), line[start:pos]


def html_links(line):
    for match in re.finditer(r'<(img|a)\b([^>]*)>', line, re.I):
        attrs = dict(re.findall(r'([\w-]+)=["\']([^"\']*)["\']', match.group(2)))
        is_image = match.group(1).lower() == 'img'
        dest = attrs.get('src' if is_image else 'href')
        if dest:
            yield is_image, attrs.get('alt', '') if is_image else 'link', dest


def has_merge_conflict(root, path):
    result = subprocess.run(
        ['git', '-C', str(root), 'ls-files', '-u', '--', relative(path, root).as_posix()],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def title(path):
    for _, line, _, _ in prose_lines(path.read_text(encoding='utf-8')):
        if line.startswith('# '):
            return line[2:].strip()
    return path.stem


def under(rel, folder):
    folder = folder.strip('/')
    return rel == folder or rel.startswith(folder + '/')


def catalog(config):
    repo = config['repos'][config['home']]
    root = repo['root']
    entries = []
    for p in documents(repo):
        rel = relative(p, root).as_posix()
        parts = rel.split('/')
        audience = 'ai' if under(rel, repo['ai']) or p.name in ['AGENTS.md', 'CLAUDE.md'] else 'human'
        kind = next((x for x in KINDS if x in parts), 'navigation')
        if any(under(rel, folder) for folder in config['compatibility']):
            kind = 'compatibility'
        entries.append({'path': rel, 'title': title(p), 'audience': audience, 'type': kind})
    human = root / repo['human']
    if human.exists():
        for p in sorted(human.rglob('*.pdf')):
            rel = relative(p, root).as_posix()
            entries.append({'path': rel, 'title': p.stem, 'audience': 'human',
                            'type': 'archive' if 'archive' in p.parts else 'reference'})
    return {'schema_version': 1, 'repository': config['home'], 'documents': sorted(entries, key=lambda x: x['path'])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--workspace', action='store_true', help='Also check sibling repositories listed in docs.config.json.')
    parser.add_argument('--write-catalog', action='store_true', help='Regenerate catalog.json before checking.')
    parser.add_argument('--root', help='Repository that owns docs.config.json. Default: parent of this script folder.')
    parser.add_argument('--config', help='Config path. Default: <root>/docs.config.json.')
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    config_path = Path(args.config).resolve() if args.config else root / 'docs.config.json'
    config = load_config(root, config_path)
    repos = config['repos']
    home = repos[config['home']]
    expected = catalog(config); catalog_path = root / 'catalog.json'
    if args.write_catalog:
        catalog_path.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    sources_path = root / home['ai'] / 'sources.json'
    sources = json.loads(sources_path.read_text(encoding='utf-8')) if sources_path.exists() else {'sources': []}
    selected = repos if args.workspace else {config['home']: home}
    selected_roots = [r['root'] for r in selected.values()]
    errors, style, skipped = [], [], []

    def owner(path):
        return next((r for r in repos.values() if relative(path, r['root']) is not None), None)

    def record(path, line, rule, detail):
        repo = owner(path)
        rel = '%s/%s' % (repo['name'], relative(path, repo['root']).as_posix()) if repo else path.as_posix()
        item = {'path': rel, 'line': line, 'rule': rule, 'detail': detail}
        (style if rule in STYLE_RULES else errors).append(item)

    paths = []
    for name, repo in selected.items():
        if not repo['root'].is_dir():
            errors.append({'path': name, 'rule': 'repository', 'detail': 'Missing sibling repository', 'line': 0}); continue
        paths += documents(repo)
    known = {urlsplit(r['url']).path.lower().rstrip('/'): r['root'] for r in repos.values() if r['url']}
    for path in paths:
        repo = owner(path)
        rel = relative(path, repo['root']).as_posix()
        if rel in repo['skipOnConflict'] and has_merge_conflict(repo['root'], path):
            skipped.append('%s/%s' % (repo['name'], rel)); continue
        text = path.read_text(encoding='utf-8'); h1 = 0; last = 0
        for line_number, line, language, is_fence in prose_lines(text):
            if is_fence and not language:
                record(path, line_number, 'fence-language', 'Code block without language')
            m = re.match(r'^(#{1,6})\s+(.+?)\s*#*$', line)
            if m:
                level = len(m.group(1)); h1 += level == 1
                if last and level > last + 1:
                    record(path, line_number, 'heading-level', line.strip())
                last = level
            links = list(markdown_links(line))
            links.extend(html_links(line))
            plain = re.sub(r'`[^`]*`', '', line)
            if config['asideDash'] and 'archive' not in path.parts and '—' in plain:
                record(path, line_number, 'aside-dash', 'Split the aside into a sentence or list item')
            reference = re.match(r'^\s{0,3}\[[^\]]+\]:\s*(<[^>]+>|\S+)', line)
            if reference:
                links.append((False, 'reference', reference.group(1).strip('<>')))
            for is_image, label, dest in links:
                if is_image and not label.strip():
                    record(path, line_number, 'image-alt', dest)
                dest = re.sub(r'\\([()])', r'\1', html.unescape(dest))
                url = urlsplit(dest)
                target = None
                if url.scheme or url.netloc:
                    if url.netloc.lower() != 'github.com':
                        continue
                    parts = unquote(url.path).split('/')
                    if len(parts) >= 6 and parts[3] in ['blob', 'tree']:
                        target_root = known.get('/'.join(parts[:3]).lower())
                        # A missing repository is already reported once; skip its links.
                        if target_root is not None and target_root in selected_roots and target_root.is_dir():
                            target = target_root / '/'.join(parts[5:])
                    if target is None:
                        continue
                elif dest.startswith('/'):
                    # Absolute server filesystem examples are not Markdown document links.
                    record(path, line_number, 'absolute-link', dest); continue
                else:
                    target = (path.parent / unquote(url.path)).resolve() if url.path else path
                if not target.exists():
                    record(path, line_number, 'missing-link', dest); continue
                if target.is_dir() and (target / 'README.md').exists():
                    target = target / 'README.md'
                if url.fragment and target.suffix.lower() == '.md':
                    if unquote(url.fragment) not in anchors(target):
                        record(path, line_number, 'missing-anchor', dest)
        if path.name != 'CLAUDE.md' and h1 != 1:
            record(path, 1, 'h1-count', str(h1))
    ids = set()
    for source in sources.get('sources', []):
        if source['id'] in ids:
            errors.append({'path': 'sources.json', 'line': 0, 'rule': 'duplicate-source', 'detail': source['id']})
        ids.add(source['id'])
        repo = repos.get(source['repository'])
        if repo and source['repository'] in selected and not (repo['root'] / source['path']).exists():
            errors.append({'path': 'sources.json', 'line': 0, 'rule': 'missing-source', 'detail': source['id']})
    if not catalog_path.exists() or json.loads(catalog_path.read_text(encoding='utf-8')) != expected:
        errors.append({'path': 'catalog.json', 'line': 0, 'rule': 'catalog-stale', 'detail': 'Run check_docs.py --write-catalog'})
    errors.extend(style)
    for issue in errors:
        print('%s:%s: %s: %s' % (issue['path'], issue['line'], issue['rule'], issue['detail']))
    print('Checked %d Markdown files; %d catalog entries; %d errors.' % (len(paths) - len(skipped), len(expected['documents']), len(errors)))
    for item in skipped:
        print('Excluded: %s (Existing merge conflict; check resumes after resolution.)' % item)
    return 1 if errors else 0


if __name__ == '__main__':
    # Windows 콘솔 기본 인코딩(cp1252 등)에서 한글 경로·문구 출력 시 UnicodeEncodeError 방지
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.exit(main())
