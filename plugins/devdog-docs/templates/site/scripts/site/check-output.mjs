import fs from 'node:fs';
import path from 'node:path';
import { load } from 'cheerio';
import { filesUnder } from './library.mjs';
import { root } from './prepare.mjs';
import { loadConfig } from './config.mjs';
const dist = path.join(root, '.site/dist');
const base = loadConfig().site.base.replace(/\/?$/, '/');
const manifest = JSON.parse(fs.readFileSync(path.join(root, '.site/manifest.json'), 'utf8'));
const files = filesUnder(dist);
const html = files.filter(f => f.endsWith('.html'));
const parsed = new Map(html.map(f => [f, load(fs.readFileSync(f, 'utf8'))]));
const errors = [];
const graph = new Map();
function checkUrl(file, href) {
  if (!href || /^(?:[a-z][\w+.-]*:|\/\/)/i.test(href)) return;
  const url = new URL(href, `https://docs.invalid${base}${path.relative(dist, file).split(path.sep).join('/')}`);
  // GitHub Pages 프로젝트 사이트는 /<저장소>/ 아래에서 제공되므로 내부 주소에 base가 있어야 함
  if (!url.pathname.startsWith(base)) { errors.push(`${path.relative(dist, file)}: missing base ${base} in ${href}`); return; }
  let target = path.join(dist, decodeURIComponent(url.pathname.slice(base.length)));
  if (target.endsWith(path.sep) || fs.existsSync(target) && fs.statSync(target).isDirectory()) target = path.join(target, 'index.html');
  if (!fs.existsSync(target)) { errors.push(`${path.relative(dist, file)}: missing ${href}`); return; }
  if (target.endsWith('.html')) {
    graph.get(file).add(target);
    if (url.hash) {
      const id = decodeURIComponent(url.hash.slice(1));
      const $ = parsed.get(target);
      if (!$ || !$('[id]').toArray().some(el => $(el).attr('id') === id)) errors.push(`${path.relative(dist, file)}: missing heading ${href}`);
    }
  }
}
for (const [file, $] of parsed) {
  graph.set(file, new Set());
  $('a[href], img[src], script[src], link[href]').each((_, el) => checkUrl(file, $(el).attr('href') || $(el).attr('src')));
}
const seen = new Set();
const queue = [path.join(dist, 'index.html')];
while (queue.length) {
  const file = queue.pop(); if (seen.has(file)) continue; seen.add(file);
  queue.push(...(graph.get(file) || []));
}
for (const entry of manifest.entries) {
  const file = path.join(dist, entry.route.slice(1));
  if (!fs.existsSync(file)) errors.push(`Missing generated file: ${entry.route}`);
  if (entry.kind === 'page' && !seen.has(file)) errors.push(`Unreachable page: ${entry.route}`);
}
for (const file of files) if (/[\\/](?:\.git|node_modules)[\\/]|[\\/](?:AGENTS|CLAUDE)\.md$|[\\/]sources\.json$/.test(file.slice(dist.length))) errors.push(`Excluded file published: ${file}`);
if (errors.length) { console.error(errors.join('\n')); process.exit(1); }
// Only public provenance is emitted. Local paths and instruction contents stay out of the website.
fs.writeFileSync(path.join(dist, 'build-info.json'), JSON.stringify({ repositories: Object.fromEntries(Object.entries(manifest.repositories).map(([id, r]) => [id, { commit: r.commit, dirty: r.dirty }])) }, null, 2) + '\n');
console.log(`Verified ${html.length} HTML pages, internal links, fragments, assets and reachability.`);
