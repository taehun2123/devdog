---
name: ko-tech-migrate
description: 기존 저장소의 한국어 문서와 코드 주석을 공학 문서체로 일괄 전환하는 절차. 사용자가 "문서 전체 문체 정리", "주석 문체 일괄 수정", "해라체를 합쇼체로 변환", "저장소 전체에 문체 규칙 적용"을 요청할 때 사용한다. 파일 몇 개를 새로 쓰는 작업에는 ko-tech-writing 스킬을 사용한다.
---

# 공학 문서체 일괄 전환

기존 저장소의 문서와 주석을 [ko-tech-writing](../ko-tech-writing/SKILL.md) 규칙으로 전환하는 절차입니다. 스크립트 경로는 이 스킬 폴더 기준 `../../scripts/`입니다. 아래 명령의 `$K`는 그 폴더입니다.

## 1. 범위와 제외 대상 확정

1. 대상 폴더를 정하십시오. 예: `docs/`, `README.md`, `src/`.
2. 다음은 제외 대상입니다. 저장소 루트의 `.ko-tech-writing.json`에 `exclude`로 등록하십시오.
   - 이미 적용된 DB 마이그레이션 파일(Flyway·Liquibase 등). 주석도 체크섬에 포함되므로 수정하면 기동이 실패합니다.
   - 생성 코드, 외부 라이브러리 복사본, 번역 원문, 법적 문서
   - 날짜가 있는 과거 기록(archive). 당시 표현을 보존합니다.
3. 도메인 용어로 쓰이는 표현은 `allow`에 등록하십시오. 예: 서비스 고유 점수명.
4. 저장소 규칙에 맞춰 `docRegister`, `commentRegister`, `commitSubject`를 설정하십시오.
5. 작업 브랜치를 만드십시오. 문서와 주석은 브랜치를 나누는 것이 리뷰에 유리합니다. 예: `docs/writing-style`, `refactor/comment-style`.

```json
{
  "docRegister": "hapsyo",
  "commentRegister": "haera",
  "exclude": ["**/db/migration/**", "**/generated/**", "docs/archive/**"],
  "allow": ["서비스 고유 용어"]
}
```

## 2. 현황 측정

```bash
python3 $K/kolint.py --json docs/ src/ > before.json
```

규칙별·파일별 건수를 집계해 사용자에게 보고하십시오. 이 수치는 완료 보고의 비교 기준입니다.

## 3. 문서 말투 변환

해라체 문서를 합쇼체로 바꾸는 경우에만 실행하십시오.

```bash
python3 $K/polite.py --dry-run --report docs/guide.md   # 디프와 검토 대상 변환 확인
python3 $K/polite.py docs/guide.md                      # 파일 수정
```

`--report`가 출력한 불규칙 변환(형용사, `~르다` 등)은 한 건씩 확인하십시오. 표·제목·코드·따옴표는 변환하지 않으므로 이후 단계에서 직접 고칩니다.

## 4. 문장·어휘 수정

1. 파일마다 `kolint.py` 결과 위치를 확인하고 규칙에 맞게 고치십시오.
2. 제목을 바꾸면 해당 제목의 앵커 링크(`#제목`)를 저장소 전체에서 찾아 함께 고치십시오.
3. 파일 이름을 바꾸면 기존 주소의 리다이렉트나 안내 파일을 추가하십시오.
4. 수정 후 해당 파일을 다시 검사하십시오.

의미 보존이 최우선입니다. 숫자·식별자·조건·예외·원인을 삭제하지 마십시오.

## 5. 코드 주석 수정

```bash
python3 $K/comment_blocks.py src/ > blocks.txt     # 위반이 있는 주석 블록과 줄 번호
```

`blocks.txt`를 읽고 블록마다 새 본문을 스펙 파일로 작성하십시오. 주석 기호와 들여쓰기는 도구가 유지하므로 본문만 씁니다.

```text
@@ src/main/java/app/CacheConfig.java:18-21
캐시 대상은 좌표 → 행정구역 변환 결과다.
같은 좌표는 항상 같은 지역을 반환하므로 오래 보관해도 안전하다.
@@ src/app/Sheet.tsx:94-94
드래그 이동량은 다시 열 때 초기화한다
```

- 한 파일의 여러 블록은 한 스펙 파일에 모아 한 번에 적용하십시오. 도구가 아래쪽 블록부터 교체하므로 줄 번호가 어긋나지 않습니다.
- `/** */` 블록은 시작 줄부터 `*/` 줄까지를 범위로 지정하십시오.
- JSX 안의 여러 줄 `{/* */}` 주석은 도구가 처리하지 않으므로 직접 수정하십시오.

```bash
python3 $K/comment_apply.py spec.txt          # 적용
python3 $K/comment_apply.py --verify          # 주석 외 코드 줄 변경 여부 검사
```

적용 후 저장소의 컴파일·타입 검사·테스트를 실행하십시오. 예: `./gradlew compileJava compileTestJava`, `npm run typecheck`.

## 6. 커밋과 보고

1. 범위별로 커밋하십시오. 예: 문서 폴더별, `components`·`screens`처럼 코드 영역별.
2. 커밋 제목은 명사형입니다. 예: `docs(guide): 문장형 제목과 표 칸 문체 수정`, `refactor(comment): 주석의 비유 표현을 기술 용어로 변경`.
3. 다시 측정하고 전후 수치를 보고하십시오.

```bash
python3 $K/kolint.py --json docs/ src/ > after.json
```

보고에는 규칙별 전후 건수, 제외한 경로와 이유, 남은 warn 항목, 실행한 검사 명령과 결과를 포함하십시오. 실행하지 않은 검사는 실행한 결과와 구분하십시오.
