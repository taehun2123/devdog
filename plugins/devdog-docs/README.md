# DevDog Docs

프로젝트 문서를 사람용·AI용으로 나누는 폴더 구조, 설정 기반 문서 검사기, 여러 저장소 문서를 모으는 위키 사이트를 설치하는 Claude Code 플러그인입니다. 넉터 프로젝트에서 운영하는 문서 체계를 다른 프로젝트에 적용하기 위해 일반화했습니다.

## 구성 요소

| 구성 요소 | 경로 | 동작 |
|---|---|---|
| 설치 스킬 `devdog-docs:init` | `skills/init/` | `docs.config.json` 작성, 폴더·README·`AGENTS.md` 규칙 섹션 생성, 검사기 설치 |
| 이전 스킬 `devdog-docs:migrate` | `skills/migrate/` | 기존 Markdown 분류, `git mv` 이동, 링크 재작성 |
| 위키 스킬 `devdog-docs:site` | `skills/site/` | VitePress 사이트 도구와 GitHub Pages 워크플로 설치 |
| 확인 스킬 `devdog-docs:check` | `skills/check/` | 기능 변경 후 문서 갱신·검사 완료 확인 |
| 생성기 | `scripts/scaffold.py` | 설정 기반 폴더·문서 생성. 여러 번 실행해도 결과 동일 |
| 이전 도구 | `scripts/inventory.py`, `scripts/apply_moves.py` | 분류 계획 초안, 계획 적용 |
| 복사 도구 | `scripts/vendor.py` | 검사기·사이트 도구 복사, 해시 잠금, 업그레이드 |
| 템플릿 | `templates/` | 문서, `AGENTS.md` 섹션, 검사기, 사이트, 워크플로 |

## 문서 구조

독자와 읽는 목적으로 문서를 나눕니다. 사람용 문서는 시작하기·작업 방법·구조 설명·규칙·값 참조 4종과 과거 자료로 구분합니다.

| 구조 | 사람용 문서 | AI용 문서 | 설정 파일 위치 |
|---|---|---|---|
| 단일 저장소 | `docs/human/` | `docs/ai/` | 저장소 루트 |
| 문서 허브 | 허브 `human/`, 코드 저장소 `docs/human/` | 허브 `ai/`, 코드 저장소 `docs/ai/` | 허브 저장소 루트 |

```text
docs/human/
├── README.md
├── tutorials/        처음 따라 해보는 일
├── how-to/           알고 있는 작업의 방법 (write-docs.md 포함)
├── explanation/      동작 원리와 설계 이유 (troubleshooting/ 장애 기록 포함)
├── reference/        정확한 값과 규칙 (document-locations.md 포함)
└── archive/          과거 보고서와 초안
docs/ai/
├── README.md         AI 작업 순서
└── sources.json      AI가 참고할 파일 목록
```

`AGENTS.md`에는 문서 위치, 기능 변경 시 문서 갱신, 장애 기록 섹션을 `<!-- devdog-docs:begin 섹션 -->` 표시 구간으로 추가합니다. 표시 구간 밖의 팀 규칙은 수정하지 않습니다. `CLAUDE.md`는 `@AGENTS.md`로 연결합니다.

## 위키 사이트

| 항목 | 내용 |
|---|---|
| 수집 | 저장소별 사람용 문서 폴더의 Markdown·이미지·PDF. AI용 문서와 `AGENTS.md`·`CLAUDE.md` 제외 |
| 주소 | `/<mount>/<경로>.html`. `README.md`는 `index.html` |
| 링크 | 수집한 문서는 사이트 주소, 그 외 파일은 GitHub 원본 커밋 주소 |
| 검색 | 로컬 검색. 한국어는 2글자 단위 토큰 추가. `archive/`는 검색 제외 |
| 문서 정보 | 원본 링크, Git 기준 마지막 수정일, 커밋하지 않은 수정 표시 |
| 배포 | GitHub Actions 빌드·검사 후 GitHub Pages 게시 |
| 허브 연동 | 코드 저장소 문서 변경 시 `repository_dispatch`로 재빌드. 미설정 시 매시 17분 예약 빌드 |

빌드 단계는 내부 링크, 제목 이동, 자산, 페이지 도달 여부, GitHub Pages `base` 경로 포함 여부를 검사합니다.

## 설치

```bash
claude plugin marketplace add taehun2123/devdog
claude plugin install devdog-docs@devdog
```

문체 검사까지 사용하려면 `devdog@devdog`도 설치하십시오. 필요한 도구는 Python 3.8 이상, Git, 위키 사이트용 Node.js 22 이상입니다.

## 사용 방법

Claude Code에서 요청하면 스킬이 적용됩니다.

| 요청 예시 | 스킬 |
|---|---|
| "이 저장소에 문서 구조 만들어줘" | init |
| "기존 docs 폴더 문서를 새 구조로 옮겨줘" | migrate |
| "문서를 GitHub Pages 위키로 게시해줘" | site |
| "작업 마무리 전에 문서 갱신 확인해줘" | check |

스크립트를 직접 실행할 수도 있습니다.

```bash
python3 scripts/scaffold.py --root <저장소> [--dry-run]
python3 scripts/vendor.py tools --root <저장소>
python3 scripts/inventory.py --root <저장소> [--repository <id>]
python3 scripts/apply_moves.py <계획 파일> --root <저장소> [--dry-run] [--stubs]
python3 scripts/vendor.py site --root <저장소> [--dry-run] [--force]
```

설정 항목은 [설정 안내](skills/init/config.md)에 있습니다.

## 업그레이드

`vendor.py`는 복사한 파일의 해시를 `.devdog-docs.json`에 기록합니다. 플러그인을 업데이트한 뒤 같은 명령을 다시 실행하면 프로젝트에서 수정하지 않은 파일만 새 버전으로 바뀝니다. 프로젝트에서 수정한 파일은 `modified`로 보고하고 유지합니다. 차이를 확인한 뒤 `--force`로 교체하십시오. `site/home.md`와 `theme/custom.css`는 최초 1회만 생성하는 프로젝트 파일입니다.

## 개발

```bash
python3 -m unittest discover -s plugins/devdog-docs/tests          # 단위 테스트
DEVDOG_DOCS_E2E=1 python3 -m unittest discover -s plugins/devdog-docs/tests -p test_site.py   # 사이트 빌드(Node.js 22, npm ci)
DEVDOG_DOCS_NUKTU=<넉터 작업 공간> DEVDOG_DOCS_NODE_MODULES=<node_modules> python3 -m unittest discover -s plugins/devdog-docs/tests -p test_nuktu_equivalence.py
claude plugin validate plugins/devdog-docs
```

`DEVDOG_DOCS_NODE_MODULES`를 지정하면 E2E 검사가 `npm ci` 대신 해당 `node_modules`를 연결합니다.

## 한계

- 위키 배포는 GitHub Pages만 워크플로로 제공합니다. 다른 호스팅은 `<site.dir>/.site/dist` 정적 파일을 직접 배포하십시오.
- 문서 사이트 접근 제어는 제공하지 않습니다. 비공개 저장소의 Pages 공개 범위는 GitHub 요금제에 따릅니다.
- 분류 초안은 파일 이름 규칙으로 만든 추정입니다. migrate 스킬이 제목·본문을 읽어 보정하고 사용자 승인을 받습니다.
- 원본 Markdown의 frontmatter는 지원하지 않습니다. 수집 단계에서 오류로 중단합니다.
