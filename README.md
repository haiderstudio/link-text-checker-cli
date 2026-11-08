# link-text-checker-cli

Check link text is useful, fail CI on click here and bare URLs.

[![CI](https://github.com/haiderstudio/link-text-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/link-text-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`link_text_checker` reads HTML and Markdown files, finds
every link, and reports each one whose visible text is
useless for a reader or a screen reader:

- A link that says "click here" tells the reader nothing,
  fails screen readers (which list links out of context),
  and tells search engines nothing about the page it
  points to. Bloggers and docs writers write them
  constantly. This tool reports every one, with its file
  and line number, and exits 1 when any problem is found
  — so it can fail a CI run. A clean folder exits 0.
- The built-in useless list is: "click here", "click
  this", "here", "read more", "learn more", "more",
  "link", "this link", "this", and "click". A link's text
  is judged as a whole, after collapsing whitespace and
  lowercasing — only an exact match is flagged, so
  "click here to read the guide" passes and "click here"
  fails. Add your own phrases with `--bad` (repeatable),
  or drop the built-in list with `--no-defaults` and use
  only your own.
- A bare URL used as the text — `[https://example.com]`
  — is flagged too: the address is not a description of
  where the link goes. A URL mentioned inside longer text
  is fine.
- An empty link is flagged, and an image link with no
  alt text is flagged — for an image link the alt text
  IS the link text, so `[![alt](img)](url)` is judged by
  its alt, and `[![](img)](url)` fails for having no alt
  text at all.
- HTML links are parsed with the standard library
  `html.parser` module, never with regex. Markdown links
  are parsed line by line with a careful regex, because
  the standard library has no Markdown parser: inline
  links `[text](url)`, reference links `[text][ref]` and
  `[text][]`, shortcut links `[text]` when a matching
  reference definition exists, autolinks
  `<https://...>`, and image links `[![alt](img)](url)`.
  Links inside fenced code blocks and inline code spans
  are examples, not real links, so they are skipped.
  Raw HTML anchors inside a Markdown file are checked
  too, as long as they are not inside a fenced code
  block.
- Links come from the command line (one or more files),
  or from a folder walk: every `.html`, `.htm`, `.md`,
  and `.markdown` file under a folder, recursively by
  default (`--no-recursive` stops at the top level).
  `.git` folders are never walked, and directory links
  are never followed, so a link cycle cannot loop the
  check.
- `--exclude PATTERN` skips files by glob, for example
  `--exclude 'draft-*'`. It can be repeated. A file passed
  directly on the command line is always checked, even if
  it has no matching extension and even if it matches an
  exclude pattern.
- `--format html` or `--format md` forces one format;
  `auto` (the default) guesses from the file extension,
  and standard input defaults to Markdown.
- `--stdin` reads one document from standard input.
- `--json` prints the result as machine-readable JSON (the
  summary goes to standard error, so standard output stays
  clean JSON).
- It is report-only and runs fully offline: it never
  fetches a URL, never rewrites a file, sends nothing
  anywhere, and needs no API key.

## What it does NOT do

- It does not check whether links work — that is Day 7's
  `broken-link-checker-cli`. This tool's one job is what
  links SAY.
- It does not check image alt text on its own — that is
  Day 30's `image-alt-checker-cli`. Alt text only matters
  here when an image IS the link.
- It does not check page titles — that is Day 50's
  `html-title-checker-cli`.
- It does not rewrite a file. A useless link is reported;
  writing better text is your job.
- It does not check a Markdown link whose text wraps
  across more than one line. Keep link text on one line.

## Who it is for

Anyone who writes docs, blog posts, or pages and wants
every link to say what it points to: a blogger checking a
batch of posts, a developer adding a CI step that fails
the build when a "click here" slips in, or anyone tidying
an old site. A useless link is invisible in the writing
itself — this catches it before it goes live.

## How this differs from similar tools

The exact name `link-text-checker-cli` matches 0
repositories on GitHub (checked Nov 8, 2026), and
`"link text checker"` quoted matches 0 too. The wider
field is big — `link text checker` unquoted matches 72
repositories — but every top result checks link HEALTH,
not link text: tcort/markdown-link-check, 723 stars,
checks whether hyperlinks are alive or dead;
lycheeverse/lychee-action, 527 stars, checks for broken
links; bmuschko/link-verifier, 28 stars, and
pythonpune/linkstatus, 8 stars, do the same. None of
them reads what the link TEXT says. The closest text
tool is Mojo-Links/anchor-text-checker, 1 star, which
fetches a live page and scores its anchor text for SEO
over-optimization — a live-page SEO analyser, not a
local-file check. None of them is a tested CLI that
walks a folder of local HTML and Markdown files, judges
each link's text, and exits 1 for CI, without ever
fetching a URL. This tool does that one job: a Python
standard-library-only CLI that checks link text in local
files — no install beyond Python, no website, no network.

## Install

Python standard library only — no packages to download. You need
Python 3.8 or newer. Clone the repo and run it in place:

```
git clone https://github.com/haiderstudio/link-text-checker-cli.git
cd link-text-checker-cli
python3 src/link_text_checker.py examples/good.html
```

```
OK — 1 file(s) checked, 3 link(s), all link text is useful.
```

## Usage

Check a good HTML file — clean, exits 0:

```
python3 src/link_text_checker.py examples/good.html
```

```
OK — 1 file(s) checked, 3 link(s), all link text is useful.
```

Check a bad HTML file — seven useless links, exits 1:

```
python3 src/link_text_checker.py examples/bad.html
```

```
FAIL examples/bad.html:8: link text "click here" — useless link text
FAIL examples/bad.html:9: link text "here" — useless link text
FAIL examples/bad.html:10: link text "Read more" — useless link text
FAIL examples/bad.html:11: link text "https://example.com" — link text is a bare URL
FAIL examples/bad.html:12: link text "" — empty link text
FAIL examples/bad.html:13: link text "" — image link has no alt text
FAIL examples/bad.html:14: link text "" — image link has no alt text
Checked 1 file(s), 8 link(s), 7 problem(s) in 1 file(s).
```

Check a good Markdown file — clean, exits 0:

```
python3 src/link_text_checker.py examples/good.md
```

```
OK — 1 file(s) checked, 4 link(s), all link text is useful.
```

Check a bad Markdown file — six useless links, exits 1:

```
python3 src/link_text_checker.py examples/bad.md
```

```
FAIL examples/bad.md:3: link text "click here" — useless link text
FAIL examples/bad.md:5: link text "here" — useless link text
FAIL examples/bad.md:7: link text "Read more" — useless link text
FAIL examples/bad.md:9: link text "https://example.com" — link text is a bare URL
FAIL examples/bad.md:11: link text "" — empty link text
FAIL examples/bad.md:13: link text "" — image link has no alt text
Checked 1 file(s), 7 link(s), 6 problem(s) in 1 file(s).
```

Check a whole folder:

```
python3 src/link_text_checker.py examples/
```

```
FAIL examples/bad.html:8: link text "click here" — useless link text
FAIL examples/bad.html:9: link text "here" — useless link text
FAIL examples/bad.html:10: link text "Read more" — useless link text
FAIL examples/bad.html:11: link text "https://example.com" — link text is a bare URL
FAIL examples/bad.html:12: link text "" — empty link text
FAIL examples/bad.html:13: link text "" — image link has no alt text
FAIL examples/bad.html:14: link text "" — image link has no alt text
FAIL examples/bad.md:3: link text "click here" — useless link text
FAIL examples/bad.md:5: link text "here" — useless link text
FAIL examples/bad.md:7: link text "Read more" — useless link text
FAIL examples/bad.md:9: link text "https://example.com" — link text is a bare URL
FAIL examples/bad.md:11: link text "" — empty link text
FAIL examples/bad.md:13: link text "" — image link has no alt text
Checked 5 file(s), 22 link(s), 13 problem(s) in 2 file(s).
```

Check one document from standard input:

```
echo '[click here](https://example.com/guide)' | python3 src/link_text_checker.py --stdin
```

```
FAIL <stdin>:1: link text "click here" — useless link text
Checked 1 file(s), 1 link(s), 1 problem(s) in 1 file(s).
```

Add your own useless phrase with `--bad` — the same
link passes without it:

```
echo '[find out more](https://example.com/guide)' | python3 src/link_text_checker.py --stdin --bad "find out more"
```

```
FAIL <stdin>:1: link text "find out more" — useless link text
Checked 1 file(s), 1 link(s), 1 problem(s) in 1 file(s).
```

```
echo '[find out more](https://example.com/guide)' | python3 src/link_text_checker.py --stdin
```

```
OK — 1 file(s) checked, 1 link(s), all link text is useful.
```

Machine-readable output with `--json` (the summary goes to
standard error, so standard output stays clean JSON):

```
python3 src/link_text_checker.py --json examples/bad.md
```

```
{
  "files": [
    {
      "file": "examples/bad.md",
      "problems": [
        {
          "line": 3,
          "text": "click here",
          "reason": "useless link text"
        },
        {
          "line": 5,
          "text": "here",
          "reason": "useless link text"
        },
        {
          "line": 7,
          "text": "Read more",
          "reason": "useless link text"
        },
        {
          "line": 9,
          "text": "https://example.com",
          "reason": "link text is a bare URL"
        },
        {
          "line": 11,
          "text": "",
          "reason": "empty link text"
        },
        {
          "line": 13,
          "text": "",
          "reason": "image link has no alt text"
        }
      ]
    }
  ],
  "summary": {
    "checked": 1,
    "links": 7,
    "files_with_problems": 1,
    "problems": 6
  }
}
```

Exit codes: 0 when every checked link has useful text,
1 when any link is useless, 2 for a usage problem (no
files given, a bad flag, or a missing file or folder).

## Examples

### 1. A bad HTML page, one of each fault

`examples/bad.html` holds eight links. Seven fail, each
for a different reason — a useless phrase, a bare URL,
an empty link, and two image links with no alt text —
and one good link passes:

```
python3 src/link_text_checker.py examples/bad.html
```

```
FAIL examples/bad.html:8: link text "click here" — useless link text
FAIL examples/bad.html:9: link text "here" — useless link text
FAIL examples/bad.html:10: link text "Read more" — useless link text
FAIL examples/bad.html:11: link text "https://example.com" — link text is a bare URL
FAIL examples/bad.html:12: link text "" — empty link text
FAIL examples/bad.html:13: link text "" — image link has no alt text
FAIL examples/bad.html:14: link text "" — image link has no alt text
Checked 1 file(s), 8 link(s), 7 problem(s) in 1 file(s).
```

### 2. A bad Markdown page, reference links included

`examples/bad.md` holds seven links, including a
reference-style link that passes and six that fail:

```
python3 src/link_text_checker.py examples/bad.md
```

```
FAIL examples/bad.md:3: link text "click here" — useless link text
FAIL examples/bad.md:5: link text "here" — useless link text
FAIL examples/bad.md:7: link text "Read more" — useless link text
FAIL examples/bad.md:9: link text "https://example.com" — link text is a bare URL
FAIL examples/bad.md:11: link text "" — empty link text
FAIL examples/bad.md:13: link text "" — image link has no alt text
Checked 1 file(s), 7 link(s), 6 problem(s) in 1 file(s).
```

### 3. The bundled examples, all at once

```
sh examples/run-example.sh
```

The script checks the good HTML file (pass), then the
bad HTML file (fail, on purpose), then the good Markdown
file (pass), then the bad Markdown file (fail, on
purpose), then the whole `examples/` folder (fail, on
purpose — it picks up both bad files). Its full output
is in `examples/sample-output.md`, ending with `Checked 5
file(s), 22 link(s), 13 problem(s) in 2 file(s).` The
failing runs exit 1, which is the expected result — the
script ends with exit 0 so it can be run as a demo.

## How it is tested

77 tests, standard library `unittest` only, no packages to install:

```
python3 tests/test_link_text_checker.py
```

The tests cover: the useless-text judgement (every
built-in phrase, case-insensitive matching, whitespace
collapsing, a phrase inside longer text passing, bare
URLs with http, https, and www, trailing punctuation,
empty text, image alt as the link text, a bad alt, an
empty or missing alt, `--bad` adding a phrase,
`--no-defaults` dropping the built-in list), HTML
parsing (nested tags, entities, the line number being
the opening tag's line, an unclosed anchor at end of
file, an anchor without href, anchors inside script,
style, and comments skipped, the title attribute not
counting, a second anchor closing the first, an empty
file), Markdown parsing (inline, full and collapsed
reference links, shortcut links with and without a
definition, autolink URLs flagged and autolink emails
left alone, a bare image not counted as a link, image
links with good, bad, and empty alt, fenced code blocks
in backticks and tildes skipped, inline code spans
skipped, definition lines skipped, two links on one
line, raw HTML anchors inside Markdown checked and
skipped inside fenced blocks, an empty file), the CLI
(exit 0/1/2, folder walking, `--no-recursive`, `.git`
skipped, `--exclude`, a direct file checked even without
a matching extension, `--format`, `--bad`,
`--no-defaults`, `--stdin` in Markdown and HTML, `--json`
output, `--version`, bad flags, missing paths, empty
folders, a non-UTF-8 file reported, input files left
unchanged), the bundled examples (sample output compared
byte-for-byte against a fresh run, and the README-quoted
outputs checked against it), and hygiene checks (no
placeholder text, no absolute paths, stdlib imports
only, `.env` first in `.gitignore`, CI file runs the
test file).

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The idea
of checking link text is not new — the similar tools
named above (the 723-star and 527-star link-health
checkers, the 1-star live-page anchor analyser) are
listed in "How this differs" — but every line of code
here is original, and the tool builds on nothing but
Python's standard library.
