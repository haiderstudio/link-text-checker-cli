#!/usr/bin/env python3
"""Check link text is useful, fail CI on click here and bare URLs.

Run: python3 src/link_text_checker.py examples/good.html
     python3 src/link_text_checker.py examples/bad.md
     python3 src/link_text_checker.py examples/

A link that says "click here" tells the reader nothing, fails
screen readers (which list links out of context), and tells
search engines nothing about the page it points to. Bloggers
and docs writers write them constantly. This tool reads HTML
and Markdown files, finds every link, and reports each one
whose visible text is useless — "click here", "here",
"read more", "link", a bare URL used as the text, or empty
text — with its file and line number, and exits 1 when any
problem is found, so it can fail a CI run. A clean folder
exits 0.

It checks what links SAY, never whether they work: it never
fetches a URL, never touches the network, and never rewrites
a file. Day 7's broken-link-checker-cli checks links work;
this one checks what they say — a different job.

HTML links are parsed with the standard library html.parser
module, never with regex. Markdown links are parsed line by
line with a careful regex, because the standard library has
no Markdown parser: inline links [text](url), reference
links [text][ref] and [text][], shortcut links [text] when
a matching reference definition exists, autolinks
<https://...>, and image links [![alt](img)](url) — where
the alt text is the link text, so an image link with no
alt text is a problem too. Links inside fenced code blocks
and inline code spans are examples, not real links, so they
are skipped. Raw HTML anchors inside a Markdown file are
checked too, as long as they are not inside a fenced code
block.

A link's text is judged as a whole, after collapsing
whitespace and lowercasing: only an exact match with a
useless phrase ("click here to read the guide" is fine,
"click here" is not) is flagged. A link with no href is
not a link and is skipped. The title attribute does not
count as link text — screen readers do not reliably read
it. A Markdown link whose text wraps across more than one
line is not checked; keep link text on one line.

Exit codes: 0 when every checked link has useful text,
1 when any link is useless, 2 for a usage or input
problem (a missing path, a bad flag, or no files to
check).

Python standard library only.
"""

import argparse
import fnmatch
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

VERSION = "1.0.0"

DEFAULT_BAD_PHRASES = (
    "click here",
    "click this",
    "here",
    "read more",
    "learn more",
    "more",
    "link",
    "this link",
    "this",
    "click",
)

HTML_EXTENSIONS = {".html", ".htm"}
MARKDOWN_EXTENSIONS = {".md", ".markdown"}
CHECK_EXTENSIONS = HTML_EXTENSIONS | MARKDOWN_EXTENSIONS

REASON_USELESS = "useless link text"
REASON_BARE_URL = "link text is a bare URL"
REASON_EMPTY = "empty link text"
REASON_NO_ALT = "image link has no alt text"

URL_SCHEMES = ("http://", "https://", "www.")

# Markdown link forms, tried in this order at each position so an
# image link is never mistaken for the image inside it, and an
# image is never mistaken for a link. Inner captures use names,
# because the named outer groups take up group numbers too.
_MD_IMAGE_LINK = r"\[\!\[(?P<img_alt>[^\]]*)\]\([^)]*\)\]\((?P<img_url>[^)]*)\)"
_MD_INLINE = r"(?<!\!)\[(?P<inline_text>[^\]]*)\]\((?P<inline_url>[^)]*)\)"
_MD_REFERENCE = r"(?<!\!)\[(?P<ref_text>[^\]]*)\]\[(?P<ref_label>[^\]]*)\]"
_MD_SHORTCUT = r"(?<!\!)\[(?P<shortcut_text>[^\]]+)\]"
_MD_LINK_RE = re.compile(
    "(?P<imglink>" + _MD_IMAGE_LINK + ")"
    "|(?P<inline>" + _MD_INLINE + ")"
    "|(?P<reference>" + _MD_REFERENCE + ")"
    "|(?P<shortcut>" + _MD_SHORTCUT + ")"
)
_MD_DEFINITION_RE = re.compile(r"^\s{0,3}\[([^\]]+)\]:\s*\S")
_MD_AUTOLINK_RE = re.compile(r"<(https?://[^>\s]+)>")
_MD_FENCE_RE = re.compile(r"^\s{0,3}(```+|~~~+)")
_MD_CODE_SPAN_RE = re.compile(r"`[^`]*`")


def normalize(text):
    """Collapse whitespace and lowercase, for comparing link text."""
    return " ".join(text.split()).lower()


def is_bare_url(text):
    """True when the whole text is a URL, ignoring trailing punctuation."""
    stripped = text.strip().rstrip(".,;:!?)")
    lowered = stripped.lower()
    return any(lowered.startswith(scheme) for scheme in URL_SCHEMES)


def evaluate_text(text, alts=None):
    """Return the problem reason for a link, or None when it is fine.

    text is the visible text; alts is the list of alt values of
    images inside the link (None where the img tag has no alt).
    The alt text is the link text when there is no visible text.
    """
    alts = alts or []
    visible = normalize(text)
    alt_texts = [normalize(a) for a in alts if a]
    combined = " ".join([visible] + alt_texts).strip()
    if not combined:
        if alts:
            return REASON_NO_ALT
        return REASON_EMPTY
    if is_bare_url(combined):
        return REASON_BARE_URL
    if combined in _BAD_PHRASES:
        return REASON_USELESS
    return None


_BAD_PHRASES = set(DEFAULT_BAD_PHRASES)


def set_bad_phrases(phrases, use_defaults=True):
    """Set the useless-phrase list (used by --bad / --no-defaults)."""
    global _BAD_PHRASES
    chosen = set(DEFAULT_BAD_PHRASES) if use_defaults else set()
    for phrase in phrases:
        cleaned = normalize(phrase)
        if cleaned:
            chosen.add(cleaned)
    _BAD_PHRASES = chosen


class _AnchorParser(HTMLParser):
    """Collect (line, text, alts) for every <a href> in HTML text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self._current = None
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "a":
            if self._current is not None:
                self._finish()
            values = dict(attrs)
            if "href" not in values:
                return
            self._current = {
                "line": self.getpos()[0],
                "parts": [],
                "alts": [],
            }
        elif tag == "img" and self._current is not None:
            values = dict(attrs)
            self._current["alts"].append(values.get("alt"))

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag == "a" and self._current is not None:
            self._finish()

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._current is not None:
            self._current["parts"].append(data)

    def close(self):
        if self._current is not None:
            self._finish()
        super().close()

    def _finish(self):
        text = "".join(self._current["parts"])
        self.links.append(
            (self._current["line"], text, self._current["alts"])
        )
        self._current = None


def check_html_text(text):
    """Return a list of (line, text, reason) for bad links in HTML."""
    parser = _AnchorParser()
    parser.feed(text)
    parser.close()
    problems = []
    for line, link_text, alts in parser.links:
        reason = evaluate_text(link_text, alts)
        if reason:
            problems.append((line, link_text, reason))
    return problems


def _fence_lines(lines):
    """Return the set of line numbers (1-based) inside fenced blocks."""
    inside = set()
    in_fence = False
    fence_char = ""
    for number, line in enumerate(lines, start=1):
        match = _MD_FENCE_RE.match(line)
        if match:
            char = match.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_char = char
                inside.add(number)
            elif char == fence_char:
                in_fence = False
                inside.add(number)
            continue
        if in_fence:
            inside.add(number)
    return inside


def _markdown_line_links(line, definitions):
    """Return [(text, alts)] for the links on one Markdown line."""
    cleaned = _MD_CODE_SPAN_RE.sub("", line)
    found = []
    for match in _MD_LINK_RE.finditer(cleaned):
        if match.group("imglink") is not None:
            alt = match.group("img_alt")
            found.append(("", [alt]))
        elif match.group("inline") is not None:
            found.append((match.group("inline_text"), []))
        elif match.group("reference") is not None:
            found.append((match.group("ref_text"), []))
        elif match.group("shortcut") is not None:
            label = normalize(match.group("shortcut_text"))
            if label in definitions:
                found.append((match.group("shortcut_text"), []))
    for match in _MD_AUTOLINK_RE.finditer(cleaned):
        found.append((match.group(1), []))
    return found


def check_markdown_text(text):
    """Return a list of (line, text, reason) for bad links in Markdown."""
    lines = text.splitlines()
    fenced = _fence_lines(lines)
    definitions = set()
    for number, line in enumerate(lines, start=1):
        if number in fenced:
            continue
        match = _MD_DEFINITION_RE.match(line)
        if match:
            definitions.add(normalize(match.group(1)))
    problems = []
    for number, line in enumerate(lines, start=1):
        if number in fenced:
            continue
        if _MD_DEFINITION_RE.match(line):
            continue
        for link_text, alts in _markdown_line_links(line, definitions):
            reason = evaluate_text(link_text, alts)
            if reason:
                problems.append((number, link_text, reason))
    # Raw HTML anchors inside the Markdown, outside fenced blocks.
    parser = _AnchorParser()
    parser.feed(text)
    parser.close()
    for line, link_text, alts in parser.links:
        if line in fenced:
            continue
        reason = evaluate_text(link_text, alts)
        if reason:
            problems.append((line, link_text, reason))
    problems.sort(key=lambda item: item[0])
    return problems


def check_text(text, fmt):
    """Check one document. fmt is "html" or "md"."""
    if fmt == "html":
        return check_html_text(text)
    return check_markdown_text(text)


def guess_format(path):
    """Return "html", "md", or None, from a file's extension."""
    suffix = Path(path).suffix.lower()
    if suffix in HTML_EXTENSIONS:
        return "html"
    if suffix in MARKDOWN_EXTENSIONS:
        return "md"
    return None


def count_links(text, fmt):
    """Count the links check_text would judge in one document."""
    if fmt == "html":
        parser = _AnchorParser()
        parser.feed(text)
        parser.close()
        return len(parser.links)
    lines = text.splitlines()
    fenced = _fence_lines(lines)
    definitions = set()
    for line in lines:
        match = _MD_DEFINITION_RE.match(line)
        if match:
            definitions.add(normalize(match.group(1)))
    count = 0
    for number, line in enumerate(lines, start=1):
        if number in fenced:
            continue
        if _MD_DEFINITION_RE.match(line):
            continue
        count += len(_markdown_line_links(line, definitions))
    parser = _AnchorParser()
    parser.feed(text)
    parser.close()
    count += sum(1 for line_no, _, _ in parser.links if line_no not in fenced)
    return count


def check_file(path, fmt=None):
    """Check one file. Returns (problems, links_checked).

    problems is a list of (line, text, reason). A file that cannot
    be read as UTF-8 text is one problem at line 0.
    """
    chosen = fmt or guess_format(path) or "md"
    try:
        text = Path(path).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return [(0, "", "cannot be read as UTF-8 text")], 0
    return check_text(text, chosen), count_links(text, chosen)


def collect_files(paths, recursive, excludes):
    """Expand files and folders into a sorted list of files to check."""
    found = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            found.append(path)
        elif path.is_dir():
            if recursive:
                for root, dirs, files in os.walk(path):
                    dirs[:] = [
                        d
                        for d in dirs
                        if d != ".git" and not (Path(root) / d).is_symlink()
                    ]
                    for name in files:
                        found.append(Path(root) / name)
            else:
                for name in sorted(os.listdir(path)):
                    child = path / name
                    if child.is_file():
                        found.append(child)
        else:
            raise FileNotFoundError(raw)
    checked = []
    for path in found:
        if path.suffix.lower() not in CHECK_EXTENSIONS:
            continue
        if any(
            fnmatch.fnmatch(path.name, pattern)
            or fnmatch.fnmatch(str(path), pattern)
            for pattern in excludes
        ):
            continue
        checked.append(path)
    return sorted(set(checked))


def display_text(text):
    """Shorten long link text for plain output; JSON keeps the full text."""
    cleaned = " ".join(text.split())
    if len(cleaned) > 80:
        return cleaned[:77] + "..."
    return cleaned


def build_parser():
    parser = argparse.ArgumentParser(
        prog="link_text_checker",
        description="Check link text is useful, fail CI on click here "
        "and bare URLs.",
    )
    parser.add_argument(
        "paths", nargs="*", help="HTML or Markdown files or folders to check"
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="read one document from standard input instead of files",
    )
    parser.add_argument(
        "--format",
        choices=["auto", "html", "md"],
        default="auto",
        help="document format: auto guesses from the file extension "
        "(standard input defaults to Markdown), html or md forces one",
    )
    parser.add_argument(
        "--bad",
        action="append",
        default=[],
        metavar="TEXT",
        help="add a phrase to the useless-text list (repeatable)",
    )
    parser.add_argument(
        "--no-defaults",
        action="store_true",
        help="drop the built-in useless-text list and use only --bad phrases",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="do not walk into subfolders",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="skip files matching this glob, by name or path (repeatable)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the result as JSON (the summary goes to standard error)",
    )
    parser.add_argument(
        "--version", action="store_true", help="print the version and exit"
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print("link-text-checker-cli " + VERSION)
        return 0
    set_bad_phrases(args.bad, use_defaults=not args.no_defaults)

    files = []
    problems_by_file = {}
    links_checked = 0

    if args.stdin:
        fmt = args.format if args.format != "auto" else "md"
        try:
            text = sys.stdin.buffer.read().decode("utf-8")
        except UnicodeDecodeError:
            problems_by_file["<stdin>"] = [
                (0, "", "cannot be read as UTF-8 text")
            ]
            files = ["<stdin>"]
            text = None
        if text is not None:
            problems = check_text(text, fmt)
            problems_by_file["<stdin>"] = problems
            files = ["<stdin>"]
            links_checked = count_links(text, fmt)
    else:
        if not args.paths:
            parser.error("no files or folders given")
        direct_files = []
        folders = []
        for raw in args.paths:
            path = Path(raw)
            if path.is_file():
                direct_files.append(path)
            elif path.is_dir():
                folders.append(path)
            else:
                print("error: no such file or folder: " + raw, file=sys.stderr)
                return 2
        found = list(direct_files)
        for folder in folders:
            found.extend(
                collect_files(
                    [folder],
                    recursive=not args.no_recursive,
                    excludes=args.exclude,
                )
            )
        seen = set()
        for path in found:
            if path in seen:
                continue
            seen.add(path)
            if any(
                fnmatch.fnmatch(path.name, pattern)
                or fnmatch.fnmatch(str(path), pattern)
                for pattern in args.exclude
            ):
                continue
            fmt = None
            if args.format != "auto":
                fmt = args.format
            problems, links = check_file(path, fmt)
            problems_by_file[str(path)] = problems
            links_checked += links
        files = sorted(problems_by_file)

    total_problems = sum(len(v) for v in problems_by_file.values())
    files_with_problems = sum(1 for v in problems_by_file.values() if v)

    if args.json:
        result = {
            "files": [
                {
                    "file": name,
                    "problems": [
                        {"line": line, "text": text, "reason": reason}
                        for line, text, reason in problems_by_file[name]
                    ],
                }
                for name in sorted(problems_by_file)
            ],
            "summary": {
                "checked": len(files),
                "links": links_checked,
                "files_with_problems": files_with_problems,
                "problems": total_problems,
            },
        }
        print(json.dumps(result, indent=2))
        print(
            "Checked {} file(s), {} link(s), {} problem(s) in {} file(s).".format(
                len(files), links_checked, total_problems, files_with_problems
            ),
            file=sys.stderr,
        )
    else:
        for name in sorted(problems_by_file):
            for line, text, reason in problems_by_file[name]:
                print(
                    'FAIL {}:{}: link text "{}" — {}'.format(
                        name, line, display_text(text), reason
                    )
                )
        if total_problems:
            print(
                "Checked {} file(s), {} link(s), {} problem(s) in {} file(s).".format(
                    len(files), links_checked, total_problems, files_with_problems
                )
            )
        else:
            print(
                "OK — {} file(s) checked, {} link(s), all link text is useful.".format(
                    len(files), links_checked
                )
            )
    return 1 if total_problems else 0


if __name__ == "__main__":
    sys.exit(main())
