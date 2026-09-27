import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), '..', 'scripts')
sys.path.insert(0, SCRIPTS)
import comment_apply  # noqa: E402
import polite  # noqa: E402


def write(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


class Polite(unittest.TestCase):
    def test_endings(self):
        cases = {
            '캐시는 5분 동안 유지된다.': '캐시는 5분 동안 유지됩니다.',
            '값이 다르다.': '값이 다릅니다.',
            '서버가 요청을 받는다.': '서버가 요청을 받습니다.',
            '기본값은 null이다.': '기본값은 null입니다.',
            '설정 파일이 있다': '설정 파일이 있습니다',
            '이미 적용했다.': '이미 적용했습니다.',
            '다음과 같다:': '다음과 같습니다:',
        }
        for src, want in cases.items():
            self.assertEqual(polite.convert(src), want, src)

    def test_protected(self):
        for src in ['# 제목을 둔다', '| 칸이다 |', '`코드이다`', '"인용이다"', '이미 합니다.', '값보다']:
            self.assertEqual(polite.convert(src), src, src)
        self.assertEqual(polite.convert('```\n유지된다.\n```'), '```\n유지된다.\n```')

    def test_uncertain_endings_are_not_corrupted(self):
        for src in ['상태가 나쁘다.', '화면이 예쁘다.', '사용자가 기쁘다.', '결과가 슬프다.', '값을 고르다.']:
            self.assertEqual(polite.convert(src), src, src)


class CommentApply(unittest.TestCase):
    def test_apply_and_verify(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, 'A.java')
            write(src, 'class A {\n    /**\n     * 서버가 죽으면\n     * 재시작한다\n     */\n'
                       '    int x = 1; // 값을 들고 있다\n}\n')
            run = dict(cwd=d, capture_output=True, text=True)
            subprocess.run(['git', 'init', '-q'], **run)
            subprocess.run(['git', 'add', '.'], **run)
            subprocess.run(['git', '-c', 'user.email=a@b', '-c', 'user.name=t', 'commit', '-qm', 'init'], **run)
            spec = os.path.join(d, 'spec.txt')
            write(spec, '@@ A.java:2-5\n서버 장애 시 재시작한다\n@@ A.java:6-6\n값을 보관한다\n')
            cwd = os.getcwd()
            os.chdir(d)
            try:
                quiet = contextlib.redirect_stdout(io.StringIO())
                quiet.__enter__()
                comment_apply.main(spec)
                with open(src, encoding='utf-8') as f:
                    self.assertEqual(f.read(), 'class A {\n    /**\n     * 서버 장애 시 재시작한다\n     */\n'
                                               '    int x = 1; // 값을 보관한다\n}\n')
                self.assertEqual(comment_apply.verify(), 0)
                write(src, 'class A {\n    int x = 2;\n}\n')
                self.assertEqual(comment_apply.verify(), 1)
            finally:
                quiet.__exit__(None, None, None)
                os.chdir(cwd)

    def test_hash_comment_render(self):
        self.assertEqual(comment_apply.render(['  # 서버가 죽으면', '  # 재시작'], ['서버 장애 시 재시작']),
                         ['  # 서버 장애 시 재시작'])

    def test_apply_preserves_crlf(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, 'A.java')
            spec = os.path.join(d, 'spec.txt')
            comment_apply.write_utf8(src, 'class A {\r\n    // 이전 주석\r\n}\r\n')
            comment_apply.write_utf8(spec, f'@@ {src}:2-2\n새 주석\n')
            with contextlib.redirect_stdout(io.StringIO()):
                comment_apply.main(spec)
            self.assertEqual(comment_apply.read_utf8(src), 'class A {\r\n    // 새 주석\r\n}\r\n')

    def test_apply_validates_all_files_before_writing(self):
        with tempfile.TemporaryDirectory() as d:
            first = os.path.join(d, 'A.java')
            second = os.path.join(d, 'B.java')
            spec = os.path.join(d, 'spec.txt')
            write(first, '// 이전 주석\n')
            write(second, 'int value = 1;\n')
            comment_apply.write_utf8(spec, f'@@ {first}:1-1\n새 주석\n@@ {second}:1-1\n변경 시도\n')
            with self.assertRaises(ValueError):
                comment_apply.main(spec)
            with open(first, encoding='utf-8') as fh:
                self.assertEqual(fh.read(), '// 이전 주석\n')

    def test_code_part_preserves_comment_markers_in_strings_and_directives(self):
        self.assertEqual(comment_apply.code_part('const url = "https://old.example";', 'A.java'),
                         'const url = "https://old.example";')
        self.assertEqual(comment_apply.code_part('value = "a # old"', 'a.py'), 'value = "a # old"')
        self.assertEqual(comment_apply.code_part('#include <old.h>', 'a.c'), '#include <old.h>')
        self.assertEqual(comment_apply.code_part('int x = 1; /* 설명 */ int y = 2;', 'a.c'),
                         'int x = 1;  int y = 2;')

    def test_verify_detects_code_that_looks_like_comments(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, 'A.java')
            write(src, 'const char* url = "https://old.example";\n#include <old.h>\n')
            run = dict(cwd=d, capture_output=True, text=True)
            subprocess.run(['git', 'init', '-q'], **run, check=True)
            subprocess.run(['git', 'add', '.'], **run, check=True)
            subprocess.run(['git', '-c', 'user.email=a@b', '-c', 'user.name=t',
                            'commit', '-qm', 'init'], **run, check=True)
            write(src, 'const char* url = "https://new.example";\n#include <new.h>\n')
            cwd = os.getcwd()
            os.chdir(d)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(comment_apply.verify(), 1)
            finally:
                os.chdir(cwd)

    def test_verify_includes_staged_and_untracked_changes(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, 'A.java')
            write(src, 'int value = 1;\n')
            run = dict(cwd=d, capture_output=True, text=True)
            subprocess.run(['git', 'init', '-q'], **run, check=True)
            subprocess.run(['git', 'add', '.'], **run, check=True)
            subprocess.run(['git', '-c', 'user.email=a@b', '-c', 'user.name=t',
                            'commit', '-qm', 'init'], **run, check=True)
            write(src, 'int value = 2;\n')
            subprocess.run(['git', 'add', 'A.java'], **run, check=True)
            cwd = os.getcwd()
            os.chdir(d)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(comment_apply.verify(), 1)
                write(src, 'int value = 1;\n')
                subprocess.run(['git', 'add', 'A.java'], **run, check=True)
                write(os.path.join(d, 'new.py'), 'value = 1\n')
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(comment_apply.verify(), 1)
            finally:
                os.chdir(cwd)


if __name__ == '__main__':
    unittest.main()
