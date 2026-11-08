#!/usr/bin/env python3
"""Tests for link-text-checker-cli. Standard library unittest only.

Run from the repo root: python3 tests/test_link_text_checker.py
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import link_text_checker as ltc  # noqa: E402

ALLOWED_STDLIB = {
    "argparse",
    "fnmatch",
    "html",
    "json",
    "os",
    "re",
    "sys",
    "pathlib",
}

BAD_HTML_EXPECTED = (
    'FAIL examples/bad.html:8: link text "click here" — useless link text\n'
    'FAIL examples/bad.html:9: link text "here" — useless link text\n'
    'FAIL examples/bad.html:10: link text "Read more" — useless link text\n'
    'FAIL examples/bad.html:11: link text "https://example.com" — link text is a bare URL\n'
    'FAIL examples/bad.html:12: link text "" — empty link text\n'
    'FAIL examples/bad.html:13: link text "" — image link has no alt text\n'
    'FAIL examples/bad.html:14: link text "" — image link has no alt text\n'
    "Checked 1 file(s), 8 link(s), 7 problem(s) in 1 file(s).\n"
)

BAD_MD_EXPECTED = (
    'FAIL examples/bad.md:3: link text "click here" — useless link text\n'
    'FAIL examples/bad.md:5: link text "here" — useless link text\n'
    'FAIL examples/bad.md:7: link text "Read more" — useless link text\n'
    'FAIL examples/bad.md:9: link text "https://example.com" — link text is a bare URL\n'
    'FAIL examples/bad.md:11: link text "" — empty link text\n'
    'FAIL examples/bad.md:13: link text "" — image link has no alt text\n'
    "Checked 1 file(s), 7 link(s), 6 problem(s) in 1 file(s).\n"
)


def run_cli(argv, stdin_bytes=None):
    """Run main() in-process and capture (exit code, stdout, stderr)."""
    ltc.set_bad_phrases([], use_defaults=True)
    out = io.StringIO()
    err = io.StringIO()
    old_stdin = sys.stdin
    if stdin_bytes is not None:
        sys.stdin = _FakeStdin(stdin_bytes)
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = ltc.main(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
    finally:
        sys.stdin = old_stdin
    return code, out.getvalue(), err.getvalue()


class _FakeStdin:
    """Minimal stdin with a .buffer, for --stdin tests."""

    def __init__(self, data):
        self.buffer = io.BytesIO(data)


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


class TestEvaluateText(unittest.TestCase):
    def test_every_default_phrase_is_useless(self):
        for phrase in ltc.DEFAULT_BAD_PHRASES:
            self.assertEqual(
                ltc.evaluate_text(phrase), ltc.REASON_USELESS, phrase
            )

    def test_phrase_match_is_case_insensitive(self):
        self.assertEqual(ltc.evaluate_text("CLICK HERE"), ltc.REASON_USELESS)
        self.assertEqual(ltc.evaluate_text("Click Here"), ltc.REASON_USELESS)
        self.assertEqual(ltc.evaluate_text("Read More"), ltc.REASON_USELESS)

    def test_phrase_match_collapses_whitespace(self):
        self.assertEqual(
            ltc.evaluate_text("  click   here\n"), ltc.REASON_USELESS
        )

    def test_phrase_inside_longer_text_is_fine(self):
        self.assertIsNone(ltc.evaluate_text("click here to read the guide"))
        self.assertIsNone(ltc.evaluate_text("read more about the release"))
        self.assertIsNone(ltc.evaluate_text("the link below explains it"))

    def test_good_text_passes(self):
        self.assertIsNone(ltc.evaluate_text("the full installation guide"))
        self.assertIsNone(ltc.evaluate_text("changelog for version 2.0"))
        self.assertIsNone(ltc.evaluate_text("Our company logo"))

    def test_bare_url_http(self):
        self.assertEqual(
            ltc.evaluate_text("https://example.com/guide"),
            ltc.REASON_BARE_URL,
        )

    def test_bare_url_http_and_www(self):
        self.assertEqual(
            ltc.evaluate_text("http://example.com"), ltc.REASON_BARE_URL
        )
        self.assertEqual(
            ltc.evaluate_text("www.example.com"), ltc.REASON_BARE_URL
        )

    def test_bare_url_ignores_trailing_punctuation(self):
        self.assertEqual(
            ltc.evaluate_text("https://example.com."), ltc.REASON_BARE_URL
        )

    def test_url_inside_longer_text_is_fine(self):
        self.assertIsNone(
            ltc.evaluate_text("Visit https://example.com for details")
        )

    def test_empty_text(self):
        self.assertEqual(ltc.evaluate_text(""), ltc.REASON_EMPTY)
        self.assertEqual(ltc.evaluate_text("   \n "), ltc.REASON_EMPTY)

    def test_image_with_alt_is_the_link_text(self):
        self.assertIsNone(ltc.evaluate_text("", ["Our company logo"]))
        self.assertEqual(
            ltc.evaluate_text("", ["click here"]), ltc.REASON_USELESS
        )

    def test_image_with_empty_alt_is_a_problem(self):
        self.assertEqual(ltc.evaluate_text("", [""]), ltc.REASON_NO_ALT)

    def test_image_with_missing_alt_is_a_problem(self):
        self.assertEqual(ltc.evaluate_text("", [None]), ltc.REASON_NO_ALT)

    def test_visible_text_plus_alt_together(self):
        self.assertIsNone(ltc.evaluate_text("See ", ["the diagram"]))

    def test_custom_bad_phrase(self):
        ltc.set_bad_phrases(["find out more"])
        self.assertEqual(
            ltc.evaluate_text("find out more"), ltc.REASON_USELESS
        )
        # --bad adds to the built-in list; it does not replace it.
        self.assertEqual(ltc.evaluate_text("click here"), ltc.REASON_USELESS)
        ltc.set_bad_phrases([], use_defaults=True)

    def test_no_defaults_drops_the_built_in_list(self):
        ltc.set_bad_phrases([], use_defaults=False)
        self.assertIsNone(ltc.evaluate_text("click here"))
        self.assertEqual(
            ltc.evaluate_text("https://example.com"), ltc.REASON_BARE_URL
        )
        ltc.set_bad_phrases([], use_defaults=True)


class TestHtmlParsing(unittest.TestCase):
    def test_simple_good_link(self):
        problems = ltc.check_html_text(
            '<a href="https://example.com">the guide</a>'
        )
        self.assertEqual(problems, [])

    def test_nested_tags_inside_link(self):
        problems = ltc.check_html_text(
            '<a href="https://example.com"><strong>click here</strong></a>'
        )
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0][2], ltc.REASON_USELESS)

    def test_entities_are_decoded(self):
        problems = ltc.check_html_text(
            '<a href="https://example.com">Tom &amp; Jerry</a>'
        )
        self.assertEqual(problems, [])

    def test_line_number_is_the_opening_tag_line(self):
        text = (
            "<p>Intro</p>\n"
            '<p><a href="https://example.com">\n'
            "click here\n"
            "</a></p>\n"
        )
        problems = ltc.check_html_text(text)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0][0], 2)

    def test_unclosed_anchor_at_end_of_file(self):
        problems = ltc.check_html_text(
            '<a href="https://example.com">click here'
        )
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0][0], 1)

    def test_anchor_without_href_is_not_a_link(self):
        problems = ltc.check_html_text('<a name="top">click here</a>')
        self.assertEqual(problems, [])

    def test_anchor_in_script_is_skipped(self):
        text = (
            "<script>\n"
            'var s = \'<a href="https://example.com">click here</a>\';\n'
            "</script>\n"
            '<a href="https://example.com">the guide</a>\n'
        )
        self.assertEqual(ltc.check_html_text(text), [])

    def test_anchor_in_style_is_skipped(self):
        text = (
            "<style>\n"
            'a::after { content: "click here"; }\n'
            "</style>\n"
            '<a href="https://example.com">click here</a>\n'
        )
        problems = ltc.check_html_text(text)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0][0], 4)

    def test_anchor_in_comment_is_skipped(self):
        text = (
            '<!-- <a href="https://example.com">click here</a> -->\n'
            '<a href="https://example.com">the guide</a>\n'
        )
        self.assertEqual(ltc.check_html_text(text), [])

    def test_title_attribute_does_not_count(self):
        problems = ltc.check_html_text(
            '<a href="https://example.com" title="the guide">click here</a>'
        )
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0][2], ltc.REASON_USELESS)

    def test_second_anchor_closes_the_first(self):
        text = (
            '<a href="https://example.com">click here\n'
            '<a href="https://example.com">the guide</a>\n'
        )
        problems = ltc.check_html_text(text)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0][0], 1)

    def test_empty_file_passes(self):
        self.assertEqual(ltc.check_html_text(""), [])


class TestMarkdownParsing(unittest.TestCase):
    def test_inline_good_and_bad(self):
        self.assertEqual(
            ltc.check_markdown_text(
                "[the guide](https://example.com/guide)\n"
            ),
            [],
        )
        problems = ltc.check_markdown_text(
            "[click here](https://example.com/guide)\n"
        )
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0], (1, "click here", ltc.REASON_USELESS))

    def test_reference_link_full_and_collapsed(self):
        text = (
            "See [the guide][g] and [the FAQ][] for help.\n"
            "\n"
            "[g]: https://example.com/guide\n"
            "[the FAQ]: https://example.com/faq\n"
        )
        self.assertEqual(ltc.check_markdown_text(text), [])

    def test_reference_link_bad_text(self):
        text = (
            "See [click here][g] for help.\n"
            "\n"
            "[g]: https://example.com/guide\n"
        )
        problems = ltc.check_markdown_text(text)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0][0], 1)

    def test_shortcut_link_with_definition(self):
        text = "[click here]\n\n[click here]: https://example.com/guide\n"
        problems = ltc.check_markdown_text(text)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0][0], 1)

    def test_shortcut_link_without_definition_is_plain_text(self):
        text = "I wrote [click here] in brackets, not as a link.\n"
        self.assertEqual(ltc.check_markdown_text(text), [])

    def test_autolink_url_is_flagged(self):
        problems = ltc.check_markdown_text(
            "Our site is <https://example.com>.\n"
        )
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0][2], ltc.REASON_BARE_URL)

    def test_autolink_email_is_fine(self):
        self.assertEqual(
            ltc.check_markdown_text("Write to <team@example.com>.\n"), []
        )

    def test_image_alone_is_not_a_link(self):
        self.assertEqual(
            ltc.check_markdown_text("![click here](logo.png)\n"), []
        )

    def test_image_link_with_good_alt_passes(self):
        self.assertEqual(
            ltc.check_markdown_text(
                "[![Our logo](logo.png)](https://example.com)\n"
            ),
            [],
        )

    def test_image_link_with_bad_alt_is_flagged(self):
        problems = ltc.check_markdown_text(
            "[![click here](logo.png)](https://example.com)\n"
        )
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0][2], ltc.REASON_USELESS)

    def test_image_link_with_empty_alt_is_flagged(self):
        problems = ltc.check_markdown_text(
            "[![](logo.png)](https://example.com)\n"
        )
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0][2], ltc.REASON_NO_ALT)

    def test_fenced_code_block_is_skipped(self):
        text = (
            "```\n"
            "[click here](https://example.com/guide)\n"
            "```\n"
            "[the guide](https://example.com/guide)\n"
        )
        self.assertEqual(ltc.check_markdown_text(text), [])

    def test_tilde_fence_is_skipped(self):
        text = (
            "~~~\n"
            "[click here](https://example.com/guide)\n"
            "~~~\n"
        )
        self.assertEqual(ltc.check_markdown_text(text), [])

    def test_inline_code_span_is_skipped(self):
        text = "Use `[click here](https://example.com)` as an example.\n"
        self.assertEqual(ltc.check_markdown_text(text), [])

    def test_definition_line_is_not_a_link(self):
        text = "[click here]: https://example.com/guide\n"
        self.assertEqual(ltc.check_markdown_text(text), [])

    def test_two_links_on_one_line(self):
        problems = ltc.check_markdown_text(
            "[click here](https://example.com/a) and "
            "[here](https://example.com/b)\n"
        )
        self.assertEqual(len(problems), 2)
        self.assertEqual(problems[0][0], 1)
        self.assertEqual(problems[1][0], 1)

    def test_raw_html_anchor_in_markdown_is_checked(self):
        problems = ltc.check_markdown_text(
            'Read <a href="https://example.com">click here</a>.\n'
        )
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0][0], 1)

    def test_raw_html_anchor_in_fenced_block_is_skipped(self):
        text = (
            "```html\n"
            '<a href="https://example.com">click here</a>\n'
            "```\n"
        )
        self.assertEqual(ltc.check_markdown_text(text), [])

    def test_empty_markdown_passes(self):
        self.assertEqual(ltc.check_markdown_text(""), [])


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._old_cwd = os.getcwd()
        os.chdir(REPO_ROOT)

    def tearDown(self):
        os.chdir(self._old_cwd)
        self.tmp.cleanup()

    def test_good_html_exit_zero(self):
        code, out, _ = run_cli(
            [str(REPO_ROOT / "examples" / "good.html")]
        )
        self.assertEqual(code, 0)
        self.assertIn(
            "OK — 1 file(s) checked, 3 link(s), all link text is useful.",
            out,
        )

    def test_bad_html_exit_one_and_exact_output(self):
        code, out, _ = run_cli(["examples/bad.html"])
        self.assertEqual(code, 1)
        self.assertEqual(out, BAD_HTML_EXPECTED)

    def test_bad_md_exit_one_and_exact_output(self):
        code, out, _ = run_cli(["examples/bad.md"])
        self.assertEqual(code, 1)
        self.assertEqual(out, BAD_MD_EXPECTED)

    def test_folder_walk(self):
        code, out, _ = run_cli([str(REPO_ROOT / "examples")])
        self.assertEqual(code, 1)
        self.assertIn(
            "Checked 5 file(s), 22 link(s), 13 problem(s) in 2 file(s).",
            out,
        )

    def test_no_recursive(self):
        write(
            self.root / "sub" / "bad.html",
            '<a href="https://example.com">click here</a>\n',
        )
        write(
            self.root / "good.html",
            '<a href="https://example.com">the guide</a>\n',
        )
        code, out, _ = run_cli(["--no-recursive", str(self.root)])
        self.assertEqual(code, 0)
        self.assertIn("1 file(s) checked", out)
        code, out, _ = run_cli([str(self.root)])
        self.assertEqual(code, 1)
        self.assertIn("2 file(s)", out)

    def test_git_folder_is_never_walked(self):
        write(
            self.root / ".git" / "evil.html",
            '<a href="https://example.com">click here</a>\n',
        )
        write(
            self.root / "good.html",
            '<a href="https://example.com">the guide</a>\n',
        )
        code, out, _ = run_cli([str(self.root)])
        self.assertEqual(code, 0)

    def test_exclude_pattern(self):
        code, out, _ = run_cli(
            ["--exclude", "bad*", str(REPO_ROOT / "examples")]
        )
        self.assertEqual(code, 0)
        self.assertIn("3 file(s) checked", out)

    def test_direct_file_without_matching_extension_is_checked(self):
        path = write(
            self.root / "notes.txt",
            "[click here](https://example.com/guide)\n",
        )
        code, out, _ = run_cli([str(path)])
        self.assertEqual(code, 1)
        self.assertIn("click here", out)

    def test_format_flag(self):
        path = write(
            self.root / "page.md",
            "[click here](https://example.com/guide)\n",
        )
        code, out, _ = run_cli(["--format", "html", str(path)])
        self.assertEqual(code, 0)
        self.assertIn("0 link(s)", out)

    def test_bad_flag_adds_a_phrase(self):
        text = b"[find out more](https://example.com/guide)\n"
        code, out, _ = run_cli(["--stdin", "--bad", "find out more"], text)
        self.assertEqual(code, 1)
        self.assertIn("find out more", out)
        code, out, _ = run_cli(["--stdin"], text)
        self.assertEqual(code, 0)

    def test_no_defaults(self):
        text = b"[click here](https://example.com/guide)\n"
        code, out, _ = run_cli(["--stdin", "--no-defaults"], text)
        self.assertEqual(code, 0)

    def test_stdin_markdown(self):
        code, out, _ = run_cli(
            ["--stdin"], b"[click here](https://example.com/guide)\n"
        )
        self.assertEqual(code, 1)
        self.assertIn('FAIL <stdin>:1: link text "click here"', out)
        self.assertIn(
            "Checked 1 file(s), 1 link(s), 1 problem(s) in 1 file(s).",
            out,
        )

    def test_stdin_html(self):
        code, out, _ = run_cli(
            ["--stdin", "--format", "html"],
            b'<a href="https://example.com">click here</a>\n',
        )
        self.assertEqual(code, 1)
        self.assertIn('FAIL <stdin>:1: link text "click here"', out)

    def test_stdin_empty_passes(self):
        code, out, _ = run_cli(["--stdin"], b"")
        self.assertEqual(code, 0)
        self.assertIn("0 link(s)", out)

    def test_json_output(self):
        code, out, err = run_cli(
            ["--json", str(REPO_ROOT / "examples" / "bad.md")]
        )
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertEqual(data["summary"]["checked"], 1)
        self.assertEqual(data["summary"]["links"], 7)
        self.assertEqual(data["summary"]["problems"], 6)
        self.assertEqual(data["summary"]["files_with_problems"], 1)
        self.assertEqual(len(data["files"][0]["problems"]), 6)
        self.assertEqual(data["files"][0]["problems"][0]["line"], 3)
        self.assertEqual(
            data["files"][0]["problems"][0]["text"], "click here"
        )
        self.assertEqual(
            data["files"][0]["problems"][0]["reason"],
            ltc.REASON_USELESS,
        )
        self.assertIn(
            "Checked 1 file(s), 7 link(s), 6 problem(s) in 1 file(s).",
            err,
        )

    def test_version(self):
        code, out, _ = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "link-text-checker-cli 1.0.0\n")

    def test_no_paths_is_usage_error(self):
        code, _, err = run_cli([])
        self.assertEqual(code, 2)

    def test_missing_path_is_usage_error(self):
        code, _, err = run_cli([str(self.root / "nope.html")])
        self.assertEqual(code, 2)
        self.assertIn("no such file or folder", err)

    def test_empty_folder(self):
        code, out, _ = run_cli([str(self.root)])
        self.assertEqual(code, 0)
        self.assertIn("0 file(s) checked", out)

    def test_non_utf8_file_is_a_problem(self):
        path = write(self.root / "bad.html", b"\xff\xfe<html>")
        code, out, _ = run_cli([str(path)])
        self.assertEqual(code, 1)
        self.assertIn("cannot be read as UTF-8 text", out)

    def test_empty_file_passes(self):
        path = write(self.root / "empty.md", "")
        code, out, _ = run_cli([str(path)])
        self.assertEqual(code, 0)

    def test_input_files_are_left_unchanged(self):
        path = write(
            self.root / "bad.md",
            "[click here](https://example.com/guide)\n",
        )
        before = path.read_bytes()
        run_cli([str(path)])
        self.assertEqual(path.read_bytes(), before)

    def test_bad_flag_value(self):
        code, _, err = run_cli(["--format", "pdf"])
        self.assertEqual(code, 2)


class TestExamples(unittest.TestCase):
    def test_sample_output_matches_a_fresh_run(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        committed = (REPO_ROOT / "examples" / "sample-output.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(result.stdout, committed)

    def test_readme_quoted_outputs_match_real_runs(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(BAD_HTML_EXPECTED.strip(), readme)
        self.assertIn(BAD_MD_EXPECTED.strip(), readme)
        self.assertIn(
            "OK — 1 file(s) checked, 3 link(s), all link text is useful.",
            readme,
        )
        self.assertIn(
            "OK — 1 file(s) checked, 4 link(s), all link text is useful.",
            readme,
        )
        code, out, _ = run_cli(["--json", str(REPO_ROOT / "examples" / "bad.md")])
        data = json.loads(out)
        self.assertIn('"text": "click here"', out)
        self.assertIn('"problems": 6', out)
        self.assertEqual(data["summary"]["problems"], 6)


class TestHygiene(unittest.TestCase):
    def test_no_placeholder_text(self):
        banned = ("TODO", "FIXME", "XXX", "coming soon", "lorem")
        for path in sorted(REPO_ROOT.rglob("*")):
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if path.is_dir() or path.name == "test_link_text_checker.py":
                continue
            text = path.read_bytes().decode("utf-8", errors="ignore")
            for word in banned:
                self.assertNotIn(
                    word, text, "{} contains {!r}".format(path, word)
                )

    def test_no_absolute_paths(self):
        for path in sorted(REPO_ROOT.rglob("*")):
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if path.is_dir() or path.name == "test_link_text_checker.py":
                continue
            text = path.read_bytes().decode("utf-8", errors="ignore")
            self.assertNotIn("/home/", text, str(path))
            self.assertNotIn("/Users/", text, str(path))

    def test_stdlib_imports_only(self):
        src = (REPO_ROOT / "src" / "link_text_checker.py").read_text(
            encoding="utf-8"
        )
        imported = set()
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("import "):
                imported.add(stripped.split()[1].split(".")[0])
            elif stripped.startswith("from "):
                imported.add(stripped.split()[1].split(".")[0])
        self.assertTrue(
            imported <= ALLOWED_STDLIB, "non-stdlib imports: {}".format(imported)
        )

    def test_env_first_in_gitignore(self):
        lines = (
            (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        )
        self.assertEqual(lines[0], ".env")

    def test_ci_file_runs_the_test_file(self):
        ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("python3 tests/test_link_text_checker.py", ci)
        self.assertIn("actions/checkout@v4", ci)
        self.assertIn("actions/setup-python@v5", ci)


if __name__ == "__main__":
    unittest.main(verbosity=2)
