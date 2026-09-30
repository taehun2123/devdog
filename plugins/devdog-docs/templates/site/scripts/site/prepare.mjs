import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { filesUnder, slash, routeFor, assertUnique, titleOf, markdown, makeResolver, rewriteTokens } from './library.mjs';
import { loadConfig, siteRoot } from './config.mjs';

export const root = siteRoot;
const output = path.join(root, '.site');
function git(directory, ...args) { return execFileSync('git', ['-C', directory, ...args], { encoding: 'utf8' }).trim(); }
function writeChanged(file, text) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  if (!fs.existsSync(file) || fs.readFileSync(file, 'utf8') !== text) fs.writeFileSync(file, text);
}
function copyChanged(source, target) {
  fs.mkdirSync(path.dirname(target), { recursive: true });
  if (!fs.existsSync(target) || !fs.readFileSync(source).equals(fs.readFileSync(target))) fs.copyFileSync(source, target);
}
/** 저장소의 사람용 문서 폴더 목록. dev.mjs가 변경 감시에 사용 */
export function watchedFolders(config = loadConfig()) {
  return Object.values(config.repositories).map(r => path.join(r.root, r.human));
}
/**
 * 문서 수집
 * - 대상: 저장소별 human 폴더의 Markdown과 이미지·PDF. AGENTS·CLAUDE·숨김 파일·심볼릭 링크 제외
 * - 주소: /<mount>/<human 기준 경로>. README.md는 index.html
 * - 링크: 수집한 문서는 사이트 주소, 그 외 파일은 GitHub 원본 커밋 주소로 변환
 * - 이전 주소: migration-map.json이 있으면 이전 경로를 새 주소로 연결
 */
export function prepare() {
  const config = loadConfig();
  const repositories = {};
  const entries = [];
  const aliases = {};
  for (const repo of Object.values(config.repositories)) {
    const { id, root: local, human: directory, mount: prefix } = repo;
    const folder = path.join(local, directory);
    if (!fs.existsSync(folder)) throw new Error(`Missing documentation: ${folder}. Check out the documentation branch or set DOCS_WORKSPACE.`);
    const dirty = Boolean(git(local, 'status', '--porcelain', '--', directory));
    const allDirty = repo.home ? Boolean(git(local, 'status', '--porcelain')) : dirty;
    if (process.env.DOCS_REQUIRE_CLEAN === '1' && allDirty) throw new Error(`Production build requires a clean checkout: ${id}`);
    repositories[id] = { url: repo.url, branch: repo.branch, root: local, commit: git(local, 'rev-parse', 'HEAD'), dirty };
    for (const file of filesUnder(folder)) {
      if (!/\.(md|png|jpe?g|webp|gif|svg|pdf)$/i.test(file) || /[\\/](AGENTS|CLAUDE)\.md$/.test(file)) continue;
      const rel = slash(path.relative(local, file));
      const md = file.endsWith('.md');
      const entry = { repository: id, path: rel, route: routeFor(prefix, path.relative(folder, file)), kind: md ? 'page' : 'asset', archive: rel.split('/').includes('archive') };
      if (md) {
        const content = fs.readFileSync(file, 'utf8');
        if (/^---\s*\n/.test(content)) throw new Error(`Source frontmatter needs an explicit mapping: ${id}/${rel}`);
        entry.title = titleOf(content);
        entry.modified = Boolean(git(local, 'status', '--porcelain', '--', rel));
        entry.updated = git(local, 'log', '-1', '--format=%cI', '--', rel) || null;
      }
      entries.push(entry);
    }
    aliases[`${id}/README.md`] = repo.home ? '/' : `/${prefix}/index.html`;
  }
  assertUnique(entries);
  const mapFile = path.join(config.repositories[config.home].root, 'migration-map.json');
  if (fs.existsSync(mapFile)) {
    // path_base "repository": { repository, from, to }. 이전 형식 "workspace": from·to가 "<저장소>/<경로>"
    for (const move of JSON.parse(fs.readFileSync(mapFile, 'utf8')).moves || []) {
      const from = move.repository ? `${move.repository}/${move.from}` : move.from;
      const to = move.repository ? `${move.repository}/${move.to}` : move.to;
      const found = entries.find(e => `${e.repository}/${e.path}` === to);
      if (found && !aliases[from]) aliases[from] = found.route;
    }
  }
  const manifest = { repositories, entries, aliases };
  const resolve = makeResolver(manifest);
  // Validate Markdown and HTML links before writing any generated content.
  for (const entry of entries.filter(e => e.kind === 'page')) {
    const text = fs.readFileSync(path.join(repositories[entry.repository].root, entry.path), 'utf8');
    rewriteTokens(markdown.parse(text, {}), href => resolve(entry, href));
  }
  const expected = new Set();
  for (const entry of entries) {
    const repo = repositories[entry.repository];
    const source = path.join(repo.root, entry.path);
    const relative = entry.route.slice(1).replace(/\.html$/, '.md');
    const target = path.join(output, entry.kind === 'page' ? 'content' : 'content/public', relative);
    expected.add(target);
    if (entry.kind === 'asset') { copyChanged(source, target); continue; }
    const fields = { title: entry.title, search: !entry.archive, source: repo.url ? `${repo.url}/blob/${repo.commit}/${entry.path.split('/').map(encodeURIComponent).join('/')}` : '', sourceModified: entry.modified, sourceUpdated: entry.updated, archive: entry.archive };
    const frontmatter = '---\n' + Object.entries(fields).map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join('\n') + '\n---\n\n';
    writeChanged(target, frontmatter + fs.readFileSync(source, 'utf8'));
  }
  // Site-owned pages and static files live in site/, not in any repository's docs.
  const home = path.join(root, 'site/home.md');
  if (fs.existsSync(home)) {
    const target = path.join(output, 'content', 'index.md');
    expected.add(target);
    writeChanged(target, fs.readFileSync(home, 'utf8'));
  }
  const publicDir = path.join(root, 'site/public');
  if (fs.existsSync(publicDir)) {
    for (const source of filesUnder(publicDir)) {
      const target = path.join(output, 'content/public', path.relative(publicDir, source));
      expected.add(target);
      copyChanged(source, target);
    }
  }
  if (fs.existsSync(path.join(output, 'content'))) {
    for (const file of filesUnder(path.join(output, 'content'))) if (!expected.has(file)) fs.unlinkSync(file);
  }
  writeChanged(path.join(output, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
  console.log(`Prepared ${entries.filter(e => e.kind === 'page').length} pages and ${entries.filter(e => e.kind === 'asset').length} assets.`);
  return manifest;
}
if (process.argv[1] === fileURLToPath(import.meta.url)) prepare();
