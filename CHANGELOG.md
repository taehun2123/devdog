# 변경 기록

## 0.4.0 (2026-09-24)

- PR 검사 추가: `gh pr create`·`gh pr edit` 실행 전 제목(`pr-title`), AI 도구 서명(`pr-signature`), 이모지(`pr-emoji`), 본문 Markdown 규칙 검사
- README에 Claude Code `attribution` 설정으로 커밋·PR 서명을 끄는 방법 추가
- 마스코트를 코드·설계 용어로 채운 타이포그래피 이미지로 교체, 다크 모드용 밝은 배경 버전(`mascot-dark.png`) 추가

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
