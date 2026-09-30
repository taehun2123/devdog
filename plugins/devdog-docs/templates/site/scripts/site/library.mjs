import fs from 'node:fs';
import path from 'node:path';
import MarkdownIt from 'markdown-it';

export const markdown = new MarkdownIt({ html: true });
export const slash = value => value.split(path.sep).join('/');
export const titleOf = text => markdown.parse(text, {}).find((t, i, all) => all[i - 1]?.tag === 'h1' && t.type === 'inline')?.content.replace(/[`*]/g, '') || '문서';
export function slugify(text) {
  return text.replace(/<[^>]*>/g, '').toLowerCase().trim().replace(/[`*~]/g, '').replace(/[^\p{L}\p{N}_ -]/gu, '').replace(/ /g, '-');
}
export function tokenize(text) {
  const words = text.toLowerCase().match(/[\p{L}\p{N}_]+/gu) || [];
  // Korean particles and compound words must also match a shorter query.
  return [...new Set(words.flatMap(word => /[가-힣]/u.test(word)
    ? [word, ...Array.from({ length: Math.max(0, word.length - 1) }, (_, i) => word.slice(i, i + 2))]
    : [word]))];
}
export function filesUnder(root) {
  return fs.readdirSync(root, { withFileTypes: true }).sort((a,b) => a.name.localeCompare(b.name, 'en')).flatMap(entry => {
    if (entry.name.startsWith('.') || entry.isSymbolicLink()) return [];
    const file = path.join(root, entry.name);
    return entry.isDirectory() ? filesUnder(file) : entry.isFile() ? [file] : [];
  });
}
export function routeFor(prefix, relative) {
  const rel = slash(relative).replace(/(^|\/)README\.md$/, '$1index.md');
  return `/${prefix}/${rel.replace(/\.md$/, '.html')}`;
}
export function assertUnique(entries) {
  const seen = new Set();
  for (const entry of entries) {
    const key = entry.route.normalize('NFC').toLowerCase();
    if (seen.has(key)) throw new Error(`Duplicate site route: ${entry.route}`);
    seen.add(key);
  }
}
export function makeResolver(manifest) {
  const byFile = new Map(manifest.entries.map(e => [`${e.repository}/${e.path}`, e]));
  for (const [key, route] of Object.entries(manifest.aliases || {})) byFile.set(key, { route });
  const repositories = manifest.repositories;
  const urls = Object.entries(repositories).map(([id, spec]) => [new URL(spec.url).pathname.toLowerCase(), id]);
  function original(id, relative, hash = '', query = '') {
    const spec = repositories[id];
    return `${spec.url}/blob/${spec.commit}/${relative.split('/').map(encodeURIComponent).join('/')}${query}${hash}`;
  }
  function resolveKey(id, relative, suffix) {
    let key = `${id}/${relative}`;
    if (!byFile.has(key) && byFile.has(`${key.replace(/\/$/, '')}/README.md`)) key = `${key.replace(/\/$/, '')}/README.md`;
    const found = byFile.get(key);
    return found ? found.route + suffix : null;
  }
  return function resolveLink(entry, href) {
    if (!href || href.startsWith('#') || /^(mailto:|tel:|data:)/i.test(href)) return href;
    let url;
    try { url = new URL(href, 'https://local.invalid'); } catch { throw new Error(`Invalid URL in ${entry.path}: ${href}`); }
    if (/^[a-z][\w+.-]*:|^\/\//i.test(href)) {
      if (url.hostname !== 'github.com') return href;
      const pathname = decodeURIComponent(url.pathname);
      const known = urls.find(([prefix]) => pathname.toLowerCase().startsWith(`${prefix}/blob/`) || pathname.toLowerCase().startsWith(`${prefix}/tree/`));
      if (!known) return href;
      const [prefix, id] = known;
      const rest = pathname.slice(prefix.length).replace(/^\/(blob|tree)\//, '');
      // Match complete source paths, including refs whose names contain slashes.
      const matches = [...byFile.keys()].filter(key => key.startsWith(`${id}/`) && rest.endsWith('/' + key.slice(id.length + 1)));
      matches.sort((a,b) => b.length - a.length);
      return matches.length ? byFile.get(matches[0]).route + url.search + url.hash : href;
    }
    if (href.startsWith('/')) throw new Error(`Unexpected absolute source link in ${entry.path}: ${href}`);
    const relative = path.posix.normalize(path.posix.join(path.posix.dirname(entry.path), decodeURIComponent(href.split(/[?#]/, 1)[0])));
    if (relative.startsWith('../')) {
      const sibling = relative.match(/^\.\.\/([^/]+)\/(.+)$/);
      const id = sibling && Object.keys(repositories).find(id => id.toLowerCase() === sibling[1].toLowerCase() || path.basename(repositories[id].root).toLowerCase() === sibling[1].toLowerCase());
      if (!id || !fs.existsSync(path.join(repositories[id].root, sibling[2]))) throw new Error(`Link escapes configured repositories in ${entry.path}: ${href}`);
      return resolveKey(id, sibling[2], url.search + url.hash) || original(id, sibling[2], url.hash, url.search);
    }
    const mapped = resolveKey(entry.repository, relative, url.search + url.hash);
    if (mapped) return mapped;
    const root = repositories[entry.repository].root;
    if (!fs.existsSync(path.join(root, relative))) throw new Error(`Missing source link in ${entry.path}: ${href}`);
    return original(entry.repository, relative, url.hash, url.search);
  };
}
export function rewriteHtml(html, rewrite) {
  return html.replace(/<(a|img)\b[^>]*>/gi, tag => tag.replace(/\b(href|src)=(['"])(.*?)\2/gi,
    (_, attr, quote, value) => `${attr}=${quote}${rewrite(value).replace(/&/g, '&amp;')}${quote}`));
}
export function rewriteTokens(tokens, rewrite) {
  for (const token of tokens) {
    for (const name of ['href', 'src']) {
      const value = token.attrGet(name);
      if (value) token.attrSet(name, rewrite(value));
    }
    if (token.type === 'html_inline' || token.type === 'html_block') token.content = rewriteHtml(token.content, rewrite);
    if (token.children) rewriteTokens(token.children, rewrite);
  }
}
