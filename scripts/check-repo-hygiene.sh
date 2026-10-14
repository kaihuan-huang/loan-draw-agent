#!/usr/bin/env bash
# Release hygiene (ENGINEERING.md §8): the shared rules file exists, and nothing is tracked that the
# deny-by-default .gitignore would exclude (local tool configuration, documents, stray exports).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
fail=0
[ -f ENGINEERING.md ] || { echo "missing ENGINEERING.md"; fail=1; }
stray="$(git ls-files -ci --exclude-standard)"
if [ -n "$stray" ]; then echo "tracked but excluded by .gitignore:"; echo "$stray" | sed 's/^/  /'; fail=1; fi
[ "$fail" -eq 0 ] && echo "repo hygiene: ok"
exit "$fail"
