import fs from 'node:fs';
import path from 'node:path';
import manifest from '../../.site/manifest.json';
import { defineConfig } from 'vitepress';
import { makeResolver, rewriteTokens, slugify, tokenize } from '../../scripts/site/library.mjs';
import { loadConfig, siteRoot } from '../../scripts/site/config.mjs';

const config = loadConfig();
const { t, site } = config;
const pages = manifest.entries.filter((e: any) => e.kind === 'page');
const routes = new Set(pages.map((e: any) => e.route));
const resolveLink = makeResolver(manifest);
const names: Record<string, string> = { ...t.folders, ...site.folderNames };
const order = ['index.html', 'tutorials', 'how-to', 'explanation', 'reference', 'archive'];
const repos = Object.values(config.repositories) as any[];
const home = repos.find(r => r.home);

function tree(items: any[], prefix: string): any[] {
  const groups = new Map<string, any[]>();
  for (const entry of items) {
    const rest = entry.route.slice(prefix.length);
    const first = rest.split('/')[0];
    if (!first || rest === 'index.html') continue;
    groups.set(first, [...(groups.get(first) || []), entry]);
  }
  return [...groups].sort(([a], [b]) => {
    const x = order.indexOf(a), y = order.indexOf(b);
    return (x < 0 ? 99 : x) - (y < 0 ? 99 : y) || a.localeCompare(b);
  }).map(([key, group]) => {
    if (key.endsWith('.html')) return { text: group[0].title, link: group[0].route };
    const index = group.find(e => e.route === `${prefix}${key}/index.html`);
    return { text: names[key] || index?.title || key, link: index?.route, collapsed: true, items: tree(group, `${prefix}${key}/`) };
  });
}
function section(text: string, prefix: string) {
  const items = pages.filter((e: any) => e.route.startsWith(prefix) && !e.archive);
  const index = items.find((e: any) => e.route === `${prefix}index.html`);
  return { text, link: index?.route, collapsed: false, items: tree(items, prefix) };
}
// 사이드바: site.sidebar({ text, prefix } 목록)가 있으면 그 순서, 없으면 저장소별 섹션
const sections = site.sidebar
  ? site.sidebar.map((s: any) => section(s.text, s.prefix))
  : repos.map(r => section(r.label, `/${r.mount}/`));
const archived = pages.filter((e: any) => e.archive);
const sidebar = [
  { text: t.allDocs, link: `/${home.mount}/index.html` },
  ...sections,
  ...(archived.length ? [{ text: t.archive, collapsed: true, items: archived.map((e: any) => ({ text: e.title, link: e.route })) }] : [])
];
const writeDocs = `/${home.mount}/how-to/write-docs.html`;
const nav = site.nav || [
  { text: t.allDocs, link: `/${home.mount}/index.html` },
  ...(routes.has(writeDocs) ? [{ text: t.writeDocs, link: writeDocs }] : [])
];
const logo = fs.existsSync(path.join(siteRoot, 'site/public/logo.svg')) ? '/logo.svg' : undefined;

export default defineConfig({
  lang: t.lang, title: site.title, description: site.description, base: site.base,
  srcDir: '../.site/content', outDir: '../.site/dist', cacheDir: '../.site/cache',
  cleanUrls: false, lastUpdated: false,
  head: [
    ...(site.noindex ? [['meta', { name: 'robots', content: 'noindex, nofollow' }]] : []),
    ...(logo ? [['link', { rel: 'icon', type: 'image/svg+xml', href: `${site.base.replace(/\/?$/, '/')}logo.svg` }]] : []),
    ['style', {}, `:root { --dd-primary: ${site.primaryColor}; }`]
  ] as any,
  markdown: {
    anchor: { slugify },
    config(md) {
      md.core.ruler.after('inline', 'source-links', state => {
        const relative = state.env.relativePath;
        const entry = pages.find((e: any) => e.route.slice(1).replace(/\.html$/, '.md') === relative);
        if (entry) rewriteTokens(state.tokens, (href: string) => resolveLink(entry, href));
      });
      const fence = md.renderer.rules.fence!;
      md.renderer.rules.fence = (tokens, index, options, env, self) => {
        if (tokens[index].info.trim() === 'mermaid') return `<MermaidDiagram code="${encodeURIComponent(tokens[index].content)}" />`;
        return fence(tokens, index, options, env, self);
      };
      const text = md.renderer.rules.text!;
      md.renderer.rules.text = (tokens, index, options, env, self) => text(tokens, index, options, env, self).replace(/\{/g, '&#123;').replace(/\}/g, '&#125;');
    }
  },
  themeConfig: {
    ...(logo ? { logo: { src: logo, alt: '' } } : {}),
    nav,
    sidebar,
    outline: { level: [2, 3], label: t.outline },
    docFooter: { prev: t.prev, next: t.next },
    sidebarMenuLabel: t.menu, returnToTopLabel: t.top, darkModeSwitchLabel: t.theme,
    sourceInfo: t.sourceInfo,
    mermaid: t.mermaid,
    search: { provider: 'local', options: {
      miniSearch: {
        ...(config.language === 'ko' ? { options: { tokenize } } : {}),
        searchOptions: { prefix: true, fuzzy: false, boost: { title: 5, titles: 3 } }
      },
      translations: { button: { buttonText: t.search.button, buttonAriaLabel: t.search.button }, modal: { displayDetails: t.search.details, resetButtonTitle: t.search.reset, backButtonTitle: t.search.back, noResultsText: t.search.empty, footer: { selectText: t.search.select, navigateText: t.search.navigate, closeText: t.search.close } } }
    } }
  } as any
});
