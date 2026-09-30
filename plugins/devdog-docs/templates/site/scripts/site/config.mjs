import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// 사이트 도구 폴더(package.json 위치). 허브는 문서 저장소 루트, 단일 저장소는 docs-site/
export const siteRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

export const labels = {
  ko: {
    lang: 'ko-KR', docs: '문서', allDocs: '전체 문서', writeDocs: '작성 안내', archive: '과거 자료', home: '안내',
    outline: '이 문서의 목차', prev: '이전 문서', next: '다음 문서', menu: '문서 메뉴', top: '맨 위로', theme: '화면 테마',
    search: { button: '문서 검색', details: '본문 미리보기', reset: '검색 지우기', back: '뒤로', empty: '검색 결과가 없습니다.', select: '선택', navigate: '이동', close: '닫기' },
    folders: { tutorials: '시작하기', 'how-to': '작업 방법', explanation: '구조 설명', reference: '규칙·값 참조', archive: '과거 자료', troubleshooting: '장애 기록' },
    sourceInfo: { label: '원본 문서 정보', archive: '과거 기록입니다. 현재 작업에는 최신 안내를 먼저 확인하십시오.', link: '원본 문서 보기', modified: '로컬 수정 내용입니다.', updated: '마지막 수정:' },
    mermaid: { label: '구조 다이어그램', source: '다이어그램 원문', error: '다이어그램을 표시하지 못했습니다. 아래 원문을 확인하십시오.' }
  },
  en: {
    lang: 'en-US', docs: 'Docs', allDocs: 'All documents', writeDocs: 'Writing guide', archive: 'Archive', home: 'Guide',
    outline: 'On this page', prev: 'Previous', next: 'Next', menu: 'Menu', top: 'Back to top', theme: 'Appearance',
    search: { button: 'Search', details: 'Show details', reset: 'Clear', back: 'Back', empty: 'No results', select: 'select', navigate: 'navigate', close: 'close' },
    folders: { tutorials: 'Tutorials', 'how-to': 'How-to guides', explanation: 'Explanation', reference: 'Reference', archive: 'Archive', troubleshooting: 'Incidents' },
    sourceInfo: { label: 'Source', archive: 'Archived record. Check the current guide first.', link: 'View source', modified: 'Local changes.', updated: 'Last updated:' },
    mermaid: { label: 'Diagram', source: 'Diagram source', error: 'The diagram could not be rendered. See the source below.' }
  }
};

export function findConfig() {
  const candidates = process.env.DOCS_CONFIG
    ? [path.resolve(process.env.DOCS_CONFIG)]
    : [path.join(siteRoot, 'docs.config.json'), path.join(siteRoot, '..', 'docs.config.json')];
  const found = candidates.find(file => fs.existsSync(file));
  if (!found) throw new Error(`docs.config.json not found near ${siteRoot}. Set DOCS_CONFIG.`);
  return found;
}

/**
 * docs.config.json 읽기
 * - 기본값: check_docs.py의 load_config와 동일(허브 저장소 human·ai, 그 외 docs/human·docs/ai)
 * - 저장소 경로: DOCS_<ID>_ROOT 우선. 없으면 허브 저장소는 설정 파일 폴더, 형제 저장소는 DOCS_WORKSPACE 기준
 */
export function loadConfig() {
  const file = findConfig();
  const data = JSON.parse(fs.readFileSync(file, 'utf8'));
  const homeRoot = path.dirname(file);
  const layout = data.layout || 'single';
  const ids = Object.keys(data.repositories);
  const home = data.home || ids.find(id => ['.', undefined].includes(data.repositories[id].local)) || ids[0];
  const workspace = process.env.DOCS_WORKSPACE || path.dirname(homeRoot);
  const language = data.project?.language === 'en' ? 'en' : 'ko';
  const t = labels[language];
  const repositories = {};
  for (const [id, spec] of Object.entries(data.repositories)) {
    const isHome = id === home;
    const override = process.env[`DOCS_${id.toUpperCase().replace(/\W/g, '_')}_ROOT`];
    repositories[id] = {
      id,
      home: isHome,
      root: override ? path.resolve(override) : isHome ? homeRoot : path.resolve(path.join(workspace, spec.local || id)),
      url: (spec.url || '').replace(/\/$/, ''),
      branch: spec.branch || 'main',
      human: spec.human || (layout === 'hub' && isHome ? 'human' : 'docs/human'),
      mount: spec.mount || id,
      label: spec.label || (isHome ? t.home : id)
    };
  }
  const project = data.project?.name || path.basename(homeRoot);
  const site = data.site || {};
  return {
    file, homeRoot, layout, home, repositories, language, project, t,
    site: {
      title: site.title || `${project} ${t.docs}`,
      description: site.description || '',
      base: site.base || '/',
      nav: site.nav,
      sidebar: site.sidebar,
      folderNames: site.folderNames || {},
      primaryColor: site.primaryColor || '#3451b2',
      noindex: site.noindex !== false,
      searchQuery: site.searchQuery || t.docs
    }
  };
}
