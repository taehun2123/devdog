---
name: migrate
description: 기존 Markdown 문서를 사람용·AI용과 문서 종류(시작하기·작업 방법·구조 설명·참조·과거 자료)로 분류해 새 폴더 구조로 옮기고 링크를 고친다. "기존 문서 정리", "docs 폴더 재구성", "문서 분류해서 옮겨줘", "문서 이전" 요청에 사용한다. init 스킬로 docs.config.json을 만든 뒤 실행한다.
---

# 기존 문서 이전

기존 Markdown 파일을 분류해 `docs.config.json`의 사람용·AI용 폴더로 옮깁니다. 이동은 `git mv`로 수행하고 모든 문서의 상대 링크와 같은 저장소 GitHub 링크를 새 경로로 고칩니다. 파일은 삭제하지 않습니다. 스크립트 경로는 이 스킬 폴더 기준 `../../scripts/`입니다.

## 전제 조건

- `docs.config.json`이 있어야 합니다. 없으면 init 스킬을 먼저 실행하십시오.
- 대상 저장소의 작업 트리가 깨끗해야 합니다. 커밋하지 않은 변경이 있으면 사용자에게 먼저 커밋할지 확인하십시오.
- 새 브랜치에서 작업하십시오. 예시는 `docs/human-ai-separation`입니다.

## 1. 분류 초안

```bash
python3 <플러그인>/scripts/inventory.py --root <설정 저장소> [--repository <저장소 id>]
```

결과는 대상 저장소의 `docs-migration-plan.json`입니다. 허브는 저장소마다 `--repository`로 실행하십시오.

- `moves`: 옮길 파일. `from`, `to`, `audience`, `kind`, `title`, `reason`
- `keep`: 제자리에 둘 파일. 저장소 루트 README·AGENTS·CLAUDE·LICENSE, 코드 폴더 옆 README, `.github/` 문서

## 2. 초안 보정

초안은 파일 이름 규칙으로 만든 추정입니다. 항목마다 제목과 첫 문단을 읽고 다음 기준으로 고치십시오.

| 내용 | 분류 |
|---|---|
| 준비물·실행 순서를 따라 하는 입문 안내 | `tutorials` |
| 이미 아는 작업의 절차·런북 | `how-to` |
| 구조·설계 이유·배경 | `explanation` |
| API·필드·명령·규칙 표 | `reference` |
| 날짜가 있는 보고서, 폐기한 규칙, 초안 | `archive` |
| AI 지시문·프롬프트·작업 규칙 | AI용 폴더 |

- 한 파일에 여러 주제가 섞여 있으면 이동만 하고, 분리는 별도 작업으로 제안하십시오.
- 같은 내용의 문서가 여러 개이면 원본 1개를 정하고 나머지는 `archive`로 옮기도록 제안하십시오.
- 영역이 여러 개이면 `human/how-to/deploy/`처럼 영역 폴더를 추가해도 됩니다.
- 파일 이름은 소문자와 하이픈을 사용합니다. 한글 이름은 유지해도 됩니다.

보정한 계획을 표(현재 경로, 새 경로, 분류, 근거)로 사용자에게 보여 주고 승인을 받으십시오. 승인 전에는 파일을 옮기지 마십시오.

## 3. 적용

```bash
python3 <플러그인>/scripts/apply_moves.py <계획 파일> --root <설정 저장소> --dry-run
python3 <플러그인>/scripts/apply_moves.py <계획 파일> --root <설정 저장소>
```

- 계획에 없는 파일, 이미 있는 대상, 저장소 밖 경로가 있으면 아무것도 옮기지 않고 종료합니다.
- 코드 블록 안의 링크는 예시이므로 고치지 않습니다.
- 이동 기록은 설정 저장소의 `migration-map.json`에 추가합니다. 위키 사이트는 이 기록으로 이전 주소를 새 주소로 연결합니다.
- 외부에서 이전 경로를 직접 참조한다면 `--stubs`로 이전 경로에 이동 안내 파일을 남기십시오.

## 4. 확인

```bash
python3 scripts/check_docs.py --write-catalog
python3 scripts/check_docs.py
python3 scripts/check_docs.py --workspace   # 허브만
```

- 새 폴더의 README 목록에 옮긴 문서를 추가하십시오.
- `AGENTS.md`, AI 참고 파일 목록(`sources.json`), 코드 주석에 이전 경로가 남아 있는지 `git grep '<이전 경로>'`로 확인하십시오.
- 다른 저장소가 이 저장소의 이전 경로를 링크하면 `--workspace` 검사에서 `missing-link`로 표시됩니다. 해당 저장소의 링크도 고치십시오.
- `docs-migration-plan.json`은 검토용 파일이므로 커밋하지 마십시오.

## 5. 보고

- 옮긴 파일 수, 분류별 개수, 제자리에 둔 파일과 이유
- 링크를 고친 파일 수와 검사 결과
- 사용자가 판단해야 할 항목: 중복 문서, 여러 주제가 섞인 문서, 분류가 모호한 문서
