# 변경 기록

## 0.1.0 (2026-09-24)

- 작성 스킬 `ko-tech-writing`: 요소별 말투, 제목·표 칸 명사형, 비유·의인화 대신 기술 용어, 부연 문장 삭제 규칙
- 일괄 전환 스킬 `ko-tech-migrate`: 측정, 합쇼체 변환, 주석 블록 교체, 코드 무변경 검증 절차
- 검사기 `kolint.py`: 규칙 9종, 저장소 설정 파일, 줄 단위 무시 주석
- 훅: 파일 작성 후 변경 줄 검사(PostToolUse), `git commit` 전 제목 검사(PreToolUse)
- 도구: `polite.py`(해라체 → 합쇼체), `comment_blocks.py`, `comment_apply.py`(`--verify`)
- 출력 스타일 `ko-tech`: 채팅 답변용, 사용자가 켤 때만 적용
