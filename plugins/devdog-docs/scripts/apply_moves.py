#!/usr/bin/env python3
"""Apply a reviewed migration plan: move files, rewrite links, record the map.

Moves use git mv when the file is tracked. Relative links in every Markdown
file of the repository are recomputed from the original locations. GitHub
links to this repository are rewritten as well. No file is deleted.
"""
import argparse
import datetime
import json
import posixpath
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / 'templates' / 'tools'))
from check_docs import html_links, load_config, markdown_links, prose_lines, relative  # noqa: E402

SKIP_DIRS = {'.git', 'node_modules', '.site'}


def validate(plan, root):
    problems, targets = [], set()
    for move in plan['moves']:
        src, dst = move['from'], move['to']
        if src == dst:
            continue
        if not (root / src).is_file():
            problems.append('missing source: %s' % src)
        if dst in targets:
            problems.append('duplicate target: %s' % dst)
        targets.add(dst)
        if (root / dst).exists():
            problems.append('target exists: %s' % dst)
        if dst.startswith('/') or '..' in dst.split('/'):
            problems.append('target outside repository: %s' % dst)
    return problems


def tracked(root, rel):
    result = subprocess.run(['git', '-C', str(root), 'ls-files', '--error-unmatch', '--', rel],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.returncode == 0


def move_file(root, src, dst):
    (root / dst).parent.mkdir(parents=True, exist_ok=True)
    if tracked(root, src):
        subprocess.run(['git', '-C', str(root), 'mv', '--', src, dst], check=True)
        return 'git mv'
    shutil.move(str(root / src), str(root / dst))
    return 'move'


def markdown_files(root):
    for path in sorted(root.rglob('*.md')):
        rel = relative(path, root)
        if not any(p in SKIP_DIRS for p in rel.parts):
            yield path


def encode_like(original, new_path):
    """Keep the original link style: percent-encoded stays encoded, raw stays raw."""
    if '%' in original or ' ' in new_path:
        return quote(new_path, safe="/()-_.~!*'")
    return new_path


def rewrite_line(line, file_old, file_new, moves, repo_url_path):
    """Return the line with every affected link destination replaced."""
    found = [dest for _, _, dest in markdown_links(line)]
    found += [dest for _, _, dest in html_links(line)]
    reference = re.match(r'^\s{0,3}\[[^\]]+\]:\s*(<[^>]+>|\S+)', line)
    if reference:
        found.append(reference.group(1).strip('<>'))
    replacements = {}
    for dest in found:
        new = rewrite_dest(dest, file_old, file_new, moves, repo_url_path)
        if new != dest:
            replacements[dest] = new
    for old, new in replacements.items():
        line = re.sub(r'(\]\(<?|\]:\s*<?|(?:src|href)=["\'])' + re.escape(old) + r'(?=[)>\s"\']|$)',
                      lambda m: m.group(1) + new, line)
    return line


def rewrite_dest(dest, file_old, file_new, moves, repo_url_path):
    url = urlsplit(dest)
    suffix = ('?' + url.query if url.query else '') + ('#' + url.fragment if url.fragment else '')
    if url.scheme or url.netloc:
        if url.netloc.lower() != 'github.com' or not repo_url_path:
            return dest
        parts = url.path.split('/')
        prefix = '/'.join(parts[:3]).lower()
        if prefix != repo_url_path or len(parts) < 6 or parts[3] not in ('blob', 'tree'):
            return dest
        rel = unquote('/'.join(parts[5:]))
        if rel not in moves:
            return dest
        head = '/'.join(parts[:5])
        return '%s://%s%s/%s%s' % (url.scheme, url.netloc, head, quote(moves[rel], safe="/()-_.~!*'"), suffix)
    if not url.path or dest.startswith('/'):
        return dest
    old_target = posixpath.normpath(posixpath.join(posixpath.dirname(file_old), unquote(url.path)))
    # Targets outside the repository (../sibling/...) keep their target; only the base may move.
    new_target = moves.get(old_target, old_target)
    if new_target == old_target and file_old == file_new:
        return dest
    new_rel = posixpath.relpath(new_target, posixpath.dirname(file_new) or '.')
    if url.path.endswith('/') and not new_rel.endswith('/'):
        new_rel += '/'
    return encode_like(url.path, new_rel) + suffix


def rewrite_links(root, moves, repo_url_path, dry_run):
    inverse = {new: old for old, new in moves.items()}
    changed = []
    for path in markdown_files(root):
        file_new = relative(path, root).as_posix()
        file_old = inverse.get(file_new, file_new)
        text = path.read_text(encoding='utf-8')
        lines = text.split('\n')
        prose = {number for number, _, _, is_fence in prose_lines(text) if not is_fence}
        out = []
        for number, line in enumerate(lines, 1):
            out.append(rewrite_line(line, file_old, file_new, moves, repo_url_path) if number in prose else line)
        new_text = '\n'.join(out)
        if new_text != text:
            changed.append(file_new)
            if not dry_run:
                path.write_text(new_text, encoding='utf-8')
    return changed


def record_map(map_path, repo_id, moves):
    data = {'schema_version': 1, 'path_base': 'repository', 'moves': []}
    if map_path.exists():
        data = json.loads(map_path.read_text(encoding='utf-8'))
    data['date'] = datetime.date.today().isoformat()
    existing = {(m.get('repository'), m['from']) for m in data['moves']}
    for src, dst in moves.items():
        if (repo_id, src) not in existing:
            data['moves'].append({'repository': repo_id, 'from': src, 'to': dst})
    map_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('plan', help='Reviewed plan from inventory.py')
    parser.add_argument('--root', default='.', help='Repository that owns docs.config.json.')
    parser.add_argument('--config')
    parser.add_argument('--stubs', action='store_true', help='Leave a short notice at each old path.')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    home_root = Path(args.root).resolve()
    config = load_config(home_root, Path(args.config).resolve() if args.config else home_root / 'docs.config.json')
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    repo = config['repos'][plan['repository']]
    root = repo['root']
    problems = validate(plan, root)
    if problems:
        for problem in problems:
            print('error     %s' % problem)
        return 1
    moves = {m['from']: m['to'] for m in plan['moves'] if m['from'] != m['to']}
    repo_url_path = urlsplit(repo['url']).path.lower().rstrip('/') if repo['url'] else ''
    for src, dst in moves.items():
        how = 'dry-run' if args.dry_run else move_file(root, src, dst)
        print('%-9s %s -> %s' % (how, src, dst))
    changed = rewrite_links(root, moves, repo_url_path, args.dry_run)
    for rel in changed:
        print('links     %s' % rel)
    if args.stubs and not args.dry_run:
        for src, dst in moves.items():
            target = posixpath.relpath(dst, posixpath.dirname(src) or '.')
            (root / src).parent.mkdir(parents=True, exist_ok=True)
            (root / src).write_text('# 이동한 문서\n\n이 문서는 [새 위치](%s)로 이동했습니다.\n' % encode_like('', target),
                                    encoding='utf-8')
            print('stub      %s' % src)
    if not args.dry_run:
        record_map(home_root / 'migration-map.json', plan['repository'], moves)
    print('%s %d files, rewrote links in %d files.' % ('Would move' if args.dry_run else 'Moved', len(moves), len(changed)))
    print('Run check_docs.py to confirm links. Links from other repositories are checked with --workspace.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
