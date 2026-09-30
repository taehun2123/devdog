# docs.config.json 설정

devdog-docs 도구가 읽는 설정 파일입니다. 위치는 단일 저장소 루트 또는 문서 허브 저장소 루트입니다.

## 전체 구조

```json
{
  "schema_version": 1,
  "layout": "hub",
  "home": "doc",
  "project": { "name": "넉터", "language": "ko" },
  "agents": { "sections": ["docs-layout", "docs-update", "incident"] },
  "repositories": {
    "doc": { "local": "doc", "url": "https://github.com/example/docs", "branch": "main", "mount": "guide" },
    "backend": { "local": "backend", "url": "https://github.com/example/backend", "branch": "dev" }
  },
  "site": { "title": "넉터 문서", "description": "개발과 운영 안내", "base": "/docs/" }
}
```

## 최상위 항목

| 키 | 기본값 | 설명 |
|---|---|---|
| `layout` | `single` | `single`(저장소 1개) 또는 `hub`(문서 저장소 + 코드 저장소 N개) |
| `home` | `local`이 `.`인 저장소 | 설정 파일과 도구를 보유한 저장소 id. 허브에서는 필수 |
| `project.name` | 폴더 이름 | 문서 제목에 표시하는 프로젝트 이름 |
| `project.language` | `ko` | `ko`이면 긴 대시 검사와 한국어 검색 토큰 사용 |
| `agents.sections` | `docs-layout`, `docs-update`, `incident` | `AGENTS.md`에 넣을 섹션. `branch-name` 추가 가능 |
| `rules.asideDash` | 언어가 `ko`이면 `true` | 긴 대시 부가 설명 검사 여부 |
| `catalog.compatibility` | 없음 | `catalog.json`에서 `compatibility` 종류로 분류할 폴더 |
| `site` | 없음 | 위키 사이트 설정. site 스킬에서 사용 |

## 저장소 항목

| 키 | 기본값 | 설명 |
|---|---|---|
| `local` | 저장소 id | 작업 공간 기준 폴더 이름. 단일 저장소는 `.` |
| `url` | 없음 | GitHub 주소. 원본 링크와 CI checkout에 사용 |
| `branch` | `main` | 위키에 게시할 브랜치 |
| `human` | 허브 저장소 `human`, 그 외 `docs/human` | 사람용 문서 폴더 |
| `ai` | 허브 저장소 `ai`, 그 외 `docs/ai` | AI용 문서 폴더 |
| `mount` | 저장소 id | 위키 주소 경로. 예: `/backend/` |
| `checkRoots` | `human`, `ai` 폴더 | 검사할 Markdown 폴더 |
| `extraDocuments` | 없음 | 문서 폴더 밖에 있어도 검사할 파일 |
| `skipOnConflict` | 없음 | 병합 충돌이 남아 있으면 검사에서 제외할 파일 |

## 사이트 항목

| 키 | 기본값 | 설명 |
|---|---|---|
| `site.title` | `project.name` + " 문서" | 사이트 제목 |
| `site.description` | 빈 값 | 검색 엔진·첫 화면 설명 |
| `site.base` | `/` | GitHub Pages 프로젝트 사이트는 `/<저장소 이름>/` |
| `site.nav` | 전체 문서, 작성 안내 | 상단 메뉴 `{ "text", "link" }` 목록 |
| `site.primaryColor` | `#3451B2` | 링크·강조 색 |
| `site.searchQuery` | `문서` | 브라우저 테스트에서 검색할 단어 |

## 환경변수

| 변수 | 용도 |
|---|---|
| `DOCS_<ID>_ROOT` | 저장소를 형제 폴더가 아닌 경로에서 읽음. 예: `DOCS_BACKEND_ROOT` |
| `DOCS_WORKSPACE` | 위키 수집 시 형제 저장소가 있는 부모 폴더 |
