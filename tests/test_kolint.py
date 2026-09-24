import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import kolint  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), 'fixtures', 'pairs.jsonl')


def write(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def cfg(**over):
    c = kolint.load_config('/nonexistent-dir')
    c.update(over)
    return c


def rules(text, name='x.md', **over):
    return [f.rule for f in kolint.lint_text(text, name, cfg(**over))]


def fixture_doc(row, key):
    line = row[key]
    if row['kind'] == 'md':
        if row['header']:
            cols = row['header'].strip().strip('|').count('|') + 1
            return row['header'] + '\n|' + '---|' * cols + '\n' + line, 'x.md'
        return line, 'x.md'
    s = line.strip()
    if s.startswith('*') and not s.startswith('*/'):
        return '/**\n' + line + '\n */', 'x' + row['ext']
    return line, 'x' + row['ext']


class FixturePairs(unittest.TestCase):
    """넉터 문체 정리 전후 줄 쌍(익명화). 수정 전은 검출, 수정 후는 통과해야 한다."""

    def test_pairs(self):
        with open(FIXTURE, encoding='utf-8') as f:
            rows = [json.loads(l) for l in f]
        c = cfg()
        missed, err_fp, warn_fp = [], [], []
        for r in rows:
            text, name = fixture_doc(r, 'before')
            got = {f.rule for f in kolint.lint_text(text, name, c)}
            if not set(r['expect']) <= got:
                missed.append((r['id'], sorted(set(r['expect']) - got)))
            text, name = fixture_doc(r, 'after')
            for f in kolint.lint_text(text, name, c):
                (err_fp if f.sev == 'error' else warn_fp).append((r['id'], f.rule))
        recall = 1 - len(missed) / len(rows)
        print(f'\n[fixture] pairs={len(rows)} recall={recall:.1%} error_fp={len(err_fp)} warn_fp={len(warn_fp)}')
        self.assertGreaterEqual(recall, 0.95, missed)
        self.assertEqual(err_fp, [])
        self.assertLessEqual(len(warn_fp) / len(rows), 0.02, warn_fp)


class Markdown(unittest.TestCase):
    def test_heading(self):
        for bad in ['## 커밋 전에', '## 무엇이 없는가', '## 서버 API가 없을 때', '## 다섯 가지 상태를 나눠 준다',
                    '### 새 테스트를 어디에 둘까', '## 캐시 전략?']:
            self.assertIn('heading-sentence', rules(bad), bad)
        for good in ['## 파일 경로', '## 응답 상태', '## 재시도 중 화면 표시', '## `deps` 변경 시 이전 응답 초기화']:
            self.assertNotIn('heading-sentence', rules(good), good)

    def test_table_cell(self):
        doc = '| 상태 | 설명 |\n|---|---|\n| pending | 아직 답이 없다 |\n| error | 실패 후 재시도 |'
        found = kolint.lint_text(doc, 'x.md', cfg())
        self.assertEqual([(f.rule, f.line) for f in found if f.rule == 'table-cell-sentence'],
                         [('table-cell-sentence', 3)])

    def test_example_column_and_multi_sentence_cell(self):
        doc = ('| 피할 표현 | 고친 표현 |\n|---|---|\n| 이게 전부입니다 | 삭제합니다. |\n\n'
               '| 증상 | 조치 |\n|---|---|\n| 배포 실패 | 로그를 확인하십시오. 원인은 대부분 설정 누락입니다. |')
        self.assertEqual(rules(doc), [])

    def test_register(self):
        self.assertIn('register-mix', rules('이 값은 서버가 계산한다.'))
        self.assertNotIn('register-mix', rules('이 값은 서버가 계산합니다.'))
        self.assertIn('register-mix', rules('이 값은 서버가 계산합니다.', docRegister='haera'))
        self.assertEqual(rules('> 인용한 원문은 그대로 둔다.'), [])

    def test_protected(self):
        doc = '```\n서버가 넘어졌다.\n```\n`답을` 이라는 변수와 "서버가 죽었다" 인용은 검사하지 않습니다.'
        self.assertNotIn('metaphor', rules(doc))

    def test_disable_line_and_allow(self):
        self.assertEqual(rules('서버가 죽었다. <!-- kolint-disable-line -->'), [])
        self.assertEqual(rules('<!-- kolint-disable-next-line -->\n서버가 죽었다.'), [])
        self.assertNotIn('metaphor', rules('손끝 점수 평균입니다.', allow=['손끝 점수']))
        self.assertEqual(rules('서버가 죽었다.', rules={'metaphor': 'off', 'register-mix': 'off'}), [])

    def test_filler_dash_particle(self):
        self.assertIn('filler', rules('이 5개가 전부입니다.'))
        self.assertIn('filler', rules('같은 값을 두 번 받는 셈입니다.'))
        self.assertIn('filler', rules('동작은 이상이 전부입니다.'))
        self.assertIn('em-dash-aside', rules('캐시를 비웁니다 — 이전 값이 남기 때문입니다.'))
        self.assertNotIn('em-dash-aside', rules('세로축은 하루(00–24시)입니다.'))
        self.assertNotIn('em-dash-aside', rules('> - 목록 항목입니다.'))
        self.assertIn('particle-spacing', rules('`ApplicationStatus` 는 6가지입니다.'))
        self.assertNotIn('particle-spacing', rules('(기본값) 이 테스트는 건너뜁니다.'))

    def test_front_matter(self):
        self.assertEqual(rules('---\ntitle: 서버가 죽었다\n---\n본문입니다.'), [])


class Comments(unittest.TestCase):
    def test_java_block_and_line(self):
        src = ('/**\n * 서버가 답을 안 주고 소켓만 붙잡고 있다.\n */\n'
               'int x = 1; // 값을 들고 있다\nString s = "서버가 죽었다";\n')
        found = kolint.lint_text(src, 'A.java', cfg())
        self.assertEqual(sorted({f.line for f in found}), [2, 4])

    def test_comment_heading_and_register(self):
        src = '/// # 캐시를 비운다\n/// 설명입니다.\n'
        self.assertIn('heading-sentence', rules(src, 'A.java'))
        self.assertNotIn('register-mix', rules(src, 'A.java'))
        self.assertIn('register-mix', rules(src, 'A.java', commentRegister='haera'))

    def test_hash_comment(self):
        self.assertIn('metaphor', rules('#!/bin/sh\nx=1  # 서버가 죽으면 재시작\n', 'run.sh'))
        self.assertEqual(rules('print("# 서버가 죽었다")\n', 'a.py'), [])


class Commit(unittest.TestCase):
    def lint(self, msg, **over):
        return [f.rule for f in kolint.lint_commit(msg, cfg(**over))]

    def test_subject(self):
        self.assertIn('commit-subject', self.lint('fix: 로그인 오류를 수정했다'))
        self.assertIn('commit-subject', self.lint('버그를 고친다.'))
        self.assertIn('commit-subject', self.lint('fix(auth): 토큰 갱신 수정해요'))
        self.assertEqual(self.lint('fix(auth): 토큰 갱신 오류 수정\n\n- 만료 임박 토큰 재발급 누락'), [])
        self.assertEqual(self.lint('Fix login bug.'), [])

    def test_body(self):
        ok = 'fix(auth): 토큰 갱신 실패 오류 수정\n\n- 만료 7일 전 갱신 요청 401 거절 원인 제거\n- 리프레시 토큰 재발급'
        self.assertEqual(self.lint(ok), [])
        self.assertIn('commit-body-style', self.lint('fix: 오류 수정\n\n토큰 갱신 로직을 고쳤습니다.'))
        self.assertIn('commit-body-style', self.lint('fix: 오류 수정\n\n- 쿼리 수를 줄였다'))
        self.assertNotIn('commit-body-style', self.lint('fix: 오류 수정\n\n토큰 갱신 로직을 고쳤습니다.', commitBody='any'))
        self.assertIn('commit-body-separator', self.lint('fix: 오류 수정\n- 원인 제거'))
        self.assertEqual(self.lint('ci: 빌더 상태 유지\n\n- 캐시 업로드 325초 소요\n- 앱 재빌드 필요'), [])
        self.assertIn('commit-body-style', self.lint('fix: 오류 수정\n\n- 재시작하면 돼요'))

    def test_file_list(self):
        self.assertIn('commit-file-list', self.lint('fix: RecruitmentServiceImpl.java 수정'))
        self.assertIn('commit-file-list', self.lint('refactor: fetchMe() 분리'))
        self.assertIn('commit-file-list', self.lint('perf: 목록 조회 개선\n\n- `UserSummaryMapper.java`: 일괄 조회 추가'))
        self.assertEqual(self.lint('perf(list): 작성자 요약 일괄 조회 적용\n\n- 쿼리 200회에서 6회로 감소'), [])

    def test_signature_and_emoji(self):
        self.assertIn('commit-signature', self.lint('feat: 캐시 추가\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'))
        self.assertIn('commit-signature', self.lint('feat: 캐시 추가\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)'))
        self.assertEqual(self.lint('feat: 캐시 추가\n\nCo-Authored-By: Kim <kim@example.com>'), [])
        self.assertIn('commit-emoji', self.lint('feat: ✨ 캐시 추가'))

    def test_trailer(self):
        msg = 'feat: 목록 캐시 추가\n\nCo-Authored-By: bot <a@b.c>'
        self.assertEqual(self.lint(msg), [])
        self.assertIn('commit-trailer', self.lint(msg, forbidTrailers=['Co-Authored-By']))

    def test_extract_messages(self):
        heredoc = "git add -A && git commit -m \"$(cat <<'EOF'\nfix: 오류를 고친다\n\n본문\nEOF\n)\""
        self.assertEqual(kolint.commit_messages(heredoc, '.'), ['fix: 오류를 고친다\n\n본문'])
        self.assertEqual(kolint.commit_messages('git commit -m "a 수정" -m "본문"', '.'), ['a 수정', '본문'])
        self.assertEqual(kolint.commit_messages('git commit -am "a 수정"', '.'), ['a 수정'])
        self.assertEqual(kolint.commit_messages('git commit --message="a 수정"', '.'), ['a 수정'])
        self.assertEqual(kolint.commit_messages('git commit', '.'), [])
        self.assertEqual(kolint.commit_messages('echo "git commit -m x"', '.'), [])
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, 'msg.txt'), 'fix: 수정\n')
            self.assertEqual(kolint.commit_messages('git commit -F msg.txt', d), ['fix: 수정\n'])


class Hooks(unittest.TestCase):
    def test_post_edit_scope(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'a.md')
            write(p, '## 기존 제목을 둔다\n\n새로 쓴 문장이다.\n')
            out = kolint.hook_post({'tool_name': 'Edit', 'tool_input': {
                'file_path': p, 'old_string': 'x', 'new_string': '새로 쓴 문장이다.'}})
            self.assertEqual(out['decision'], 'block')
            self.assertIn(f'{p}:3', out['reason'])
            self.assertNotIn(f'{p}:1', out['reason'])

    def test_post_warn_only_and_clean(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'a.md')
            write(p, '값을 들고 있습니다.\n')
            out = kolint.hook_post({'tool_name': 'Write', 'tool_input': {'file_path': p, 'content': ''}})
            self.assertIn('additionalContext', out['hookSpecificOutput'])
            write(p, '값을 보관합니다.\n')
            self.assertEqual(kolint.hook_post({'tool_name': 'Write', 'tool_input': {'file_path': p}}), {})

    def test_post_respects_exclude(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, kolint.CONFIG_NAME), '{"exclude": ["db/**"]}')
            os.makedirs(os.path.join(d, 'db'))
            p = os.path.join(d, 'db', 'V1.sql')
            write(p, '-- 서버가 죽었다\n')
            self.assertEqual(kolint.hook_post({'tool_input': {'file_path': p}}), {})

    def test_pre_commit_deny(self):
        out = kolint.hook_pre({'cwd': '/nonexistent', 'tool_input': {'command': 'git commit -m "fix: 오류를 고친다"'}})
        hso = out['hookSpecificOutput']
        self.assertEqual(hso['permissionDecision'], 'deny')
        self.assertIn('commit-subject', hso['permissionDecisionReason'])
        self.assertEqual(kolint.hook_pre({'tool_input': {'command': 'git commit -m "fix: 오류 수정"'}}), {})
        self.assertEqual(kolint.hook_pre({'tool_input': {'command': 'ls -la'}}), {})


if __name__ == '__main__':
    unittest.main()
