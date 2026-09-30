---
name: site
description: 사람용 문서를 메뉴·검색이 있는 위키 사이트(VitePress)로 만들고 GitHub Pages 자동 배포 워크플로를 설치한다. 문서 허브 구조에서는 여러 저장소의 문서를 한 사이트로 모으고 코드 저장소에 재빌드 알림 워크플로를 추가한다. "문서 위키 만들어줘", "문서 사이트 배포", "GitHub Pages로 문서 게시", "여러 저장소 문서 한 곳에서 보기" 요청에 사용한다.
---

# 위키 사이트 설치

`docs.config.json`의 저장소별 사람용 문서 폴더를 모아 VitePress 사이트를 만들고 GitHub Pages로 게시합니다. 스크립트 경로는 이 스킬 폴더 기준 `../../scripts/`입니다. 설정 항목은 [설정 안내](../init/config.md)에 있습니다.

## 전제 조건

- init 스킬로 `docs.config.json`과 폴더 구조를 만든 상태여야 합니다.
- 모든 저장소에 GitHub `url`과 게시할 `branch`가 있어야 합니다.
- Node.js 22 이상과 npm이 필요합니다.

## 1. 사이트 설정

`docs.config.json`에 `site` 항목을 추가하십시오.

| 항목 | 결정 기준 |
|---|---|
| `site.base` | 사이트 주소 `https://<소유자>.github.io/<저장소>/`이면 `/<저장소>/`. 사용자 지정 도메인이면 `/` |
| `site.title`, `site.description` | 첫 화면 제목과 설명 |
| `site.primaryColor` | 링크·강조 색. 프로젝트 디자인 시스템 색 |
| `site.searchQuery` | 문서에 실제로 있는 단어. 브라우저 테스트에서 검색 결과를 확인 |
| `site.dir` | 사이트 도구 폴더. 기본값은 허브 `.`, 단일 저장소 `docs-site` |

## 2. 도구 설치

```bash
python3 <플러그인>/scripts/vendor.py site --root <설정 저장소> --dry-run
python3 <플러그인>/scripts/vendor.py site --root <설정 저장소>
```

| 생성 파일 | 내용 |
|---|---|
| `<site.dir>/package.json`, `package-lock.json`, `.nvmrc` | VitePress·Playwright 개발 의존성 |
| `<site.dir>/scripts/site/` | 문서 수집(`prepare.mjs`), 결과 검사, 미리보기 서버 |
| `<site.dir>/site/.vitepress/` | 사이트 설정과 테마. 프로젝트 스타일은 `theme/custom.css` |
| `<site.dir>/site/home.md` | 첫 화면. 최초 1회만 생성하고 이후 수정은 프로젝트가 관리 |
| `.github/workflows/docs-pages.yml` | 빌드·검사·GitHub Pages 게시 |
| 코드 저장소 `.github/workflows/notify-docs.yml` | 허브만. 문서 변경 시 재빌드 요청 |
| `.gitignore` | `node_modules`, `.site` 등 빌드 결과 제외 |

`home.md`와 `custom.css`를 제외한 파일은 업그레이드 대상입니다. 프로젝트에서 수정한 파일은 `vendor.py`가 덮어쓰지 않고 `modified`로 보고합니다.

## 3. 로컬 확인

`<site.dir>`에서 실행하십시오.

```bash
npm install
npm test
npm run docs:build
npm run docs:preview
```

- `docs:build`는 문서 수집, VitePress 빌드, 결과 검사를 순서대로 실행합니다. 결과 검사는 내부 링크·제목 이동·자산·도달 가능 여부와 `site.base` 경로 포함 여부를 확인합니다.
- 수집 대상은 사람용 문서 폴더의 Markdown과 이미지·PDF입니다. AI용 문서, `AGENTS.md`, `CLAUDE.md`는 게시하지 않습니다.
- 수집하지 않은 파일로 가는 링크는 GitHub 원본 커밋 주소로 바뀝니다.
- 원본 Markdown에 frontmatter가 있으면 수집을 중단합니다. frontmatter를 제거하거나 본문으로 옮기십시오.
- `archive/` 문서는 기본 검색에서 제외하고 사이드바의 과거 자료에 표시합니다.
- 브라우저 검사는 `npx playwright install chromium` 후 `npm run test:browser`로 실행하십시오.

`package-lock.json`을 설치한 버전으로 갱신했다면 함께 커밋하십시오. CI는 `npm ci`로 설치합니다.

## 4. GitHub 설정

다음 항목은 사용자가 GitHub에서 설정해야 합니다. 외부 게시이므로 적용 전에 사용자에게 확인하십시오.

1. 설정 저장소의 Settings > Pages > Source를 GitHub Actions로 바꾸십시오.
2. 허브는 코드 저장소 checkout용 secret `DOCS_SOURCE_TOKEN`을 설정 저장소에 등록하십시오. 권한은 코드 저장소 Contents 읽기입니다. 공개 저장소만 있으면 생략할 수 있습니다.
3. 허브의 코드 저장소에는 secret `DOCS_DISPATCH_TOKEN`을 등록하십시오. 권한은 설정 저장소 Contents 쓰기(repository_dispatch)입니다. 등록하지 않으면 매시 17분 예약 빌드로 반영됩니다.
4. 비공개 저장소의 Pages는 GitHub 요금제에 따라 사용할 수 없거나 사이트가 공개될 수 있습니다. 공개 범위를 사용자에게 확인하십시오.

## 5. 보고

- 생성·갱신·보존(`modified`, `kept`) 파일 목록
- `npm test`, `docs:build`, 브라우저 검사 결과. 실행하지 않은 검사는 구분하십시오.
- 사용자가 할 GitHub 설정 항목과 예상 사이트 주소

GitHub Pages 대신 자체 서버에 배포하려면 `docs:build` 결과 폴더 `<site.dir>/.site/dist`를 정적 파일로 제공하십시오.
