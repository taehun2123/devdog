# ko-tech-writing

개발팀의 한국어 기술 문서, 커밋 메시지, 코드 주석을 공학 문서체로 작성·검사하는 Claude Code 플러그인입니다. 작성 규칙(스킬), 결정적 검사기(`kolint.py`), 자동 검사 훅, 기존 저장소 일괄 전환 도구로 구성됩니다.

```text
수정 전  ## 서버가 넘어졌을 때 무슨 일이 일어나는가
수정 후  ## 서버 장애 시 처리

수정 전  | 대기 | 아직 답이 없다 |
수정 후  | 대기 | 아직 응답을 받지 못함 |

수정 전  fix: 로그인 오류를 고쳤다
수정 후  fix(auth): 토큰 갱신 실패 오류 수정
```

## 다른 한국어 플러그인과의 차이

범용 "자연스러운 한국어", "AI 티 제거" 플러그인은 이미 여럿 있습니다([fluent-korean](https://github.com/snflkd/fluent-korean), [k-skill](https://github.com/NomaDamas/k-skill), [korean-skills](https://github.com/DaleSeo/korean-skills) 등). 이 플러그인의 대상은 개발 조직의 공학 문서입니다.

| 항목 | 범용 한국어 플러그인 | ko-tech-writing |
|---|---|---|
| 목표 | 사람다운 글 | 사실·조건·절차를 한 번에 찾는 글 |
| 적용 대상 | 채팅 답변, Markdown | Markdown, 커밋 메시지, 코드 주석 |
| 말투 규칙 | 전체 일관성 | 요소별 규칙(본문 `~입니다`, 절차 `~하십시오`, 제목·표 칸 명사형) |
| 어휘 | 번역투 일반 | 개발 문맥의 비유·의인화 사전("서버가 넘어졌다" → "서버 오류") |
| 외래어 | 순화어 권장 경우 있음 | 통용 외래어 우선(커밋, 머지, 스펙) |
| 검사 방식 | 프롬프트 지침 | 정규식 검사기 + 훅 + 테스트 fixture |
| 기존 저장소 | 텍스트 단위 윤문 | 일괄 전환 절차와 코드 무변경 검증 |

## 구성 요소

| 구성 요소 | 경로 | 동작 |
|---|---|---|
| 작성 스킬 | `skills/ko-tech-writing/` | 한국어 문서·커밋·주석 작성 시 자동 적용 |
| 전환 스킬 | `skills/ko-tech-migrate/` | 저장소 전체 문체 정리 요청 시 적용 |
| 검사기 | `scripts/kolint.py` | 규칙 9종 검사, CLI·훅 겸용 |
| 파일 검사 훅 | `hooks/hooks.json` (PostToolUse) | Write·Edit 후 변경된 줄만 검사, 위반 위치를 Claude에 전달 |
| 커밋 검사 훅 | `hooks/hooks.json` (PreToolUse) | `git commit -m` 제목 검사, 위반 시 실행 거부 |
| 전환 도구 | `scripts/polite.py`, `comment_blocks.py`, `comment_apply.py` | 해라체 → 합쇼체 변환, 주석 블록 교체, 코드 무변경 검증 |
| 출력 스타일 | `output-styles/ko-tech.md` | 채팅 답변용, 사용자가 켤 때만 적용 |

규칙을 모든 답변에 상시 주입하지 않습니다. 상시 주입하면 답변에서 정보가 누락되는 사례가 보고되어([korean-kit](https://github.com/IsthisLee/korean-kit)) 스킬과 파일 검사 훅으로 범위를 제한했습니다.

## 설치

```bash
claude plugin marketplace add taehun2123/ko-tech-writing
claude plugin install ko-tech-writing@ko-tech-writing
```

`python3` 3.8 이상이 필요합니다. 스크립트는 표준 라이브러리만 사용합니다. macOS에서 확인했으며 Windows는 확인하지 않았습니다.

## 사용 방법

### 자동 적용

설치 후 한국어 문서·주석·커밋을 요청하면 작성 스킬이 적용됩니다. Claude가 파일을 쓰면 훅이 변경된 줄을 검사하고, error 등급 위반이 있으면 같은 턴에서 수정하도록 전달합니다.

### 직접 검사

```bash
python3 scripts/kolint.py docs/ src/                 # 문서와 코드 주석
python3 scripts/kolint.py --json docs/ > report.json  # JSON 출력
python3 scripts/kolint.py --commit-msg .git/COMMIT_EDITMSG
```

error 등급 위반이 있으면 종료 코드 1을 반환하므로 CI나 git `commit-msg` 훅에 연결할 수 있습니다.

### 기존 저장소 전환

"저장소 전체 문서 문체를 정리해 줘"처럼 요청하면 `ko-tech-migrate` 스킬의 절차(측정 → 변환 → 디프 검토 → 컴파일 검사 → 범위별 커밋)로 진행합니다.

## 검사 규칙

| 규칙 | 등급 | 검출 대상 |
|---|---|---|
| `heading-sentence` | error | 문장·의문문·"~때"·조사로 끝나는 제목 |
| `table-cell-sentence` | error | "~다"로 끝나는 한 문장 표 칸 |
| `register-mix` | error | 설정한 말투와 다른 종결어미 |
| `filler` | error | "이게 전부입니다", "~하는 셈입니다" 등 부연 문장 |
| `commit-subject` | error | 문장형으로 끝나는 커밋 제목 |
| `commit-trailer` | error | 설정으로 금지한 커밋 트레일러 |
| `metaphor` | warn | 비유·의인화·대화체 어휘 약 50종 |
| `em-dash-aside` | warn | 긴 대시 부가 설명 |
| `particle-spacing` | warn | 영문·코드·숫자 뒤 조사 띄어쓰기 |

코드 블록, 인라인 코드, 따옴표, URL, 인용 블록의 말투, 예시 문장 열("수정 전", "표현" 등)은 검사하지 않습니다. 줄 끝에 `kolint-disable-line`, 앞 줄에 `kolint-disable-next-line` 주석을 두면 해당 줄을 제외합니다.

## 설정

저장소 루트의 `.ko-tech-writing.json`으로 기본값을 바꿉니다. 검사 대상 파일에서 상위 폴더 방향으로 가장 가까운 파일을 사용합니다.

```json
{
  "docRegister": "hapsyo",
  "commentRegister": "haera",
  "commitSubject": "noun",
  "forbidTrailers": ["Co-Authored-By"],
  "exclude": ["**/db/migration/**", "docs/archive/**"],
  "allow": ["서비스 고유 용어"],
  "rules": { "particle-spacing": "off", "metaphor": "error" }
}
```

| 키 | 기본값 | 값 |
|---|---|---|
| `docRegister` | `hapsyo` | 문서 본문 말투. `hapsyo`(~입니다), `haera`(~이다), `any` |
| `commentRegister` | `any` | 코드 주석 말투. 값은 `docRegister`와 같음 |
| `commitSubject` | `noun` | 커밋 제목 형식. `noun`, `any` |
| `forbidTrailers` | `[]` | 금지할 커밋 트레일러 이름 |
| `exclude` | 빌드 산출물·의존성 폴더 | 추가로 제외할 glob |
| `allow` | `[]` | 검사하지 않을 어구 |
| `rules` | 규칙별 기본 등급 | `error`, `warn`, `off` |

## 측정 결과

실제 서비스 저장소 5곳(문서 3곳, 코드 2곳)의 문체 정리 디프에서 수정 전후 줄 8,022쌍을 추출해 측정했습니다.

| 지표 | 값 |
|---|---|
| 수정 전 줄 검출률 (전체 규칙) | 48.4% |
| 수정 후 줄 오탐률 (전체 규칙) | 0.54% |
| 수정 후 줄 오탐률 (error 등급) | 0.01% (1건, 실제 남은 위반) |
| 익명화 fixture 168쌍 검출률 | 98.8% |
| 익명화 fixture 오탐 | 0건 |

수정 전 줄 검출률이 50% 미만인 이유는 번역투 재구성처럼 정규식으로 판별할 수 없는 수정이 포함되기 때문입니다. 이 영역은 작성 스킬이 담당합니다. 검사기는 오탐을 줄이는 방향으로 조정했습니다.

플러그인 있음·없음 비교 결과는 [evals/README.md](evals/README.md)에 있습니다.

## 한계

- 형태소 분석 없이 정규식으로 검사합니다. 동음이의어(예: 실제 그림을 "그린다")는 warn 등급으로 보고되며, 문맥 판단은 Claude나 사람이 합니다.
- 번역투 문장 구조, 불필요한 명사화, 문장 길이는 검사하지 않습니다.
- 커밋 검사 훅은 `-m`, `--message`, `-F` 형식만 확인합니다. 편집기로 작성한 커밋 메시지는 `--commit-msg` 옵션을 git 훅에 연결하십시오.

## 개발

```bash
python3 -m unittest discover -s tests   # 단위 테스트와 fixture 검사
python3 evals/ablation.py --runs 2       # 플러그인 있음·없음 비교 (Claude 사용량 발생)
claude plugin validate .claude-plugin/plugin.json
```

## 라이선스

MIT
