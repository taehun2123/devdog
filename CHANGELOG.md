# 변경 기록

## 미출시

- Windows 기본 인코딩과 관계없이 주석 전환 스펙·소스·Git 디프를 UTF-8로 처리
- 주석 전환 시 기존 줄바꿈 형식 보존, 전체 스펙 검증 후 파일 기록
- 코드 무변경 검증에서 staged 변경, 바이너리 변경, 새 코드 파일 포함
- URL 문자열·전처리문·문자열 내부 주석 기호를 코드로 판정
- 안전하게 활용할 수 없는 `~르다`·`~쁘다`·`~프다` 표현의 자동 변환 제외
- Ubuntu·macOS·Windows, Python 3.8·3.14 테스트 워크플로 추가

## 0.6.0 (2026-09-26)

- 읽기 어려운 번역어 규칙 추가(`plain-term`): `크래시`·`단언`·`전송 차단` → `강제 종료`·`필수 조건`·`전송되지 않음`
- 용어 대응표에 번역어 절과 도메인 용어 기준 추가, `막히다` 항목에 메시지 전송 예외 추가

## 0.5.0 (2026-09-25)

- 순우리말 동작 동사 규칙 추가(`native-verb`): `두다`·`늘리다`·`줄이다`·`넘다` → `설정`·`확대`·`축소`·`초과`
- 서술형 주석 블록 규칙 추가(`comment-narrative`): 항목 없이 `~다` 문장이 3개 이상인 주석 블록 검출
- 작성 스킬의 코드 주석 규칙에 명사형 제목과 `- 라벨: 내용` 항목 형식 추가, 용어 대응표에 동작 동사 절 추가
- 일괄 전환 스킬의 주석 스펙 예시를 항목 형식으로 변경

## 0.4.0 (2026-09-24)

- PR 검사 추가: `gh pr create`·`gh pr edit` 실행 전 제목(`pr-title`), AI 도구 서명(`pr-signature`), 이모지(`pr-emoji`), 본문 Markdown 규칙 검사
- README에 Claude Code `attribution` 설정으로 커밋·PR 서명을 끄는 방법 추가
- 마스코트를 일러스트 이미지로 교체

## 0.3.0 (2026-09-24)

- 커밋 본문 규칙 추가: 제목·본문 사이 빈 줄(`commit-body-separator`), 짧은 개조식 본문(`commit-body-style`)
- 커밋 금지 항목 검사 추가: AI 도구 서명·공동작업 표기(`commit-signature`), 이모지(`commit-emoji`), 파일·함수 이름 나열(`commit-file-list`)
- 설정 키 `commitBody` 추가 (`bullet` 기본값, `any`)
- 해요체 판정 수정: "필요", "소요"처럼 "요"로 끝나는 명사는 문장형으로 판정하지 않음
- 작성 스킬 규칙 문서의 커밋 메시지 절을 제목·본문·금지 항목으로 재작성
- `git commit -v` 구분선 아래 디프를 커밋 메시지 검사에서 제외
- README 검사 규칙을 문서·주석 표와 커밋 메시지 표로 분리, 비교 이미지에 커밋 본문·서명 예시 추가

## 0.2.0 (2026-09-24)

- 플러그인 이름을 `ko-tech-writing`에서 DevDog(식별자 `devdog`)으로 변경
- 스킬 이름 변경: `ko-tech-writing` → `devdog:writing`, `ko-tech-migrate` → `devdog:migrate`
- 출력 스타일 이름 변경: `ko-tech` → `devdog`
- 설정 파일 이름 변경: `.ko-tech-writing.json` → `.devdog.json`
- 저장소 주소 변경: `taehun2123/ko-tech-writing` → `taehun2123/devdog`
- 설치 명령 변경: `claude plugin marketplace add taehun2123/devdog`, `claude plugin install devdog@devdog`
- 마스코트 이미지 추가: README 상단과 적용 전후 비교 이미지에 표시

## 0.1.0 (2026-09-24)

- 작성 스킬 `ko-tech-writing`: 요소별 말투, 제목·표 칸 명사형, 비유·의인화 대신 기술 용어, 부연 문장 삭제 규칙
- 일괄 전환 스킬 `ko-tech-migrate`: 측정, 합쇼체 변환, 주석 블록 교체, 코드 무변경 검증 절차
- 검사기 `kolint.py`: 규칙 9종, 저장소 설정 파일, 줄 단위 무시 주석
- 훅: 파일 작성 후 변경 줄 검사(PostToolUse), `git commit` 전 제목 검사(PreToolUse)
- 도구: `polite.py`(해라체 → 합쇼체), `comment_blocks.py`, `comment_apply.py`(`--verify`)
- 출력 스타일 `ko-tech`: 채팅 답변용, 사용자가 켤 때만 적용
