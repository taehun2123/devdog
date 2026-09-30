---
name: init
description: 프로젝트에 사람용·AI용 문서 폴더 구조, AGENTS.md 문서 규칙, 설정 기반 문서 검사기를 설치한다. "문서 구조 만들어줘", "docs 폴더 구조 적용", "AGENTS.md에 문서 갱신 규칙 추가", "문서 허브 구성", "devdog-docs 설치" 요청에 사용한다. 기존 문서 이동은 migrate, 위키 사이트는 site 스킬이 담당한다.
---

# 문서 구조 설치

`docs.config.json` 설정 1개로 문서 폴더, 폴더 README, `AGENTS.md` 규칙 섹션, 문서 검사기를 설치합니다. 스크립트 경로는 이 스킬 폴더 기준 `../../scripts/`입니다.

## 1. 구조 결정

| 조건 | 구조 |
|---|---|
| 저장소 1개에 코드와 문서가 함께 있음 | `single`: `docs/human/`, `docs/ai/` |
| 같은 부모 폴더에 코드 저장소가 여러 개 있고 공통 문서 저장소가 있거나 새로 만듦 | `hub`: 문서 저장소 `human/`·`ai/` + 코드 저장소 `docs/human/`·`docs/ai/` |

판단이 어려우면 사용자에게 구조와 저장소 목록을 확인하십시오. 허브에서 문서 저장소가 없으면 새 폴더를 만들고 `git init` 여부를 사용자에게 확인하십시오.

## 2. 설정 작성

저장소 루트(허브는 문서 저장소 루트)에 `docs.config.json`을 작성하십시오. 항목은 [설정 안내](config.md)에 있습니다.

- `url`은 `git remote get-url origin`으로 확인하십시오. SSH 주소는 `https://github.com/<소유자>/<저장소>` 형식으로 바꾸십시오.
- `branch`는 위키에 게시할 브랜치입니다. 코드 저장소는 보통 개발 기본 브랜치입니다.
- 허브에는 `home`을 반드시 지정하십시오.

## 3. 생성

먼저 변경 예정 목록을 확인하십시오.

```bash
python3 <플러그인>/scripts/scaffold.py --root <저장소> --dry-run
python3 <플러그인>/scripts/scaffold.py --root <저장소>
python3 <플러그인>/scripts/vendor.py tools --root <저장소>
```

- `scaffold.py`는 없는 파일만 만듭니다. 기존 README·문서 본문은 수정하지 않습니다.
- `AGENTS.md`에는 `<!-- devdog-docs:begin 섹션 -->` 표시 구간만 추가·갱신합니다. 표시 구간 밖의 팀 규칙은 유지합니다.
- `CLAUDE.md`가 없으면 `@AGENTS.md` 한 줄로 만듭니다. 이미 있으면 `AGENTS.md`를 참조하는지 확인하고, 참조하지 않으면 사용자에게 추가 여부를 확인하십시오.
- `vendor.py tools`는 `scripts/check_docs.py`와 `.github/workflows/docs-check.yml`을 복사하고 `.devdog-docs.json`에 해시를 기록합니다.

## 4. 검사

```bash
python3 scripts/check_docs.py --write-catalog
python3 scripts/check_docs.py
python3 scripts/check_docs.py --workspace   # 허브만
```

오류가 있으면 원인을 고친 뒤 다시 실행하십시오. 기존 문서에서 나온 오류는 목록으로 보고하고 migrate 스킬로 정리할지 사용자에게 확인하십시오.

## 5. 보고

- 생성·갱신한 파일 수와 주요 경로
- 검사 명령과 결과
- 커밋 여부. 커밋은 사용자 확인 후 저장소별로 수행하십시오.

기존 문서를 새 구조로 옮기려면 migrate 스킬, 위키 사이트가 필요하면 site 스킬을 이어서 실행하십시오.
