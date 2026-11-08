#!/bin/sh
# Check the bundled examples. The failing runs exit 1 on purpose,
# so each one ends with "|| true"; the script itself ends with
# exit 0 so it can be run as a demo. Run from the repo root:
# sh examples/run-example.sh
cd "$(dirname "$0")/.."
echo "== good.html: all link text is useful =="
python3 src/link_text_checker.py examples/good.html || true
echo
echo "== bad.html: seven useless links =="
python3 src/link_text_checker.py examples/bad.html || true
echo
echo "== good.md: all link text is useful =="
python3 src/link_text_checker.py examples/good.md || true
echo
echo "== bad.md: six useless links =="
python3 src/link_text_checker.py examples/bad.md || true
echo
echo "== examples/: the whole folder =="
python3 src/link_text_checker.py examples/ || true
