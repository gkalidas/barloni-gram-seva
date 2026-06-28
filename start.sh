#!/usr/bin/env bash
# One-click launcher for barloni-gram-seva (macOS / Linux).
# Double-click it (if your file manager allows running scripts) or run:
#     ./start.sh
set -u
cd "$(dirname "$0")" || exit 1

# Find a usable Python 3.10+, preferring one that already has pip.
PYTHON=""
FALLBACK=""
for cand in python3 python3.12 python3.11 python3.10 python; do
    if command -v "$cand" >/dev/null 2>&1; then
        ok=$("$cand" -c 'import sys; print(1 if sys.version_info[:2] >= (3,10) else 0)' 2>/dev/null)
        if [ "$ok" = "1" ]; then
            if "$cand" -m pip --version >/dev/null 2>&1; then
                PYTHON="$cand"
                break
            fi
            [ -z "$FALLBACK" ] && FALLBACK="$cand"
        fi
    fi
done
[ -z "$PYTHON" ] && PYTHON="$FALLBACK"

if [ -z "$PYTHON" ]; then
    echo
    echo "Python 3.10 or newer was not found on this computer."
    echo "Please install it from https://www.python.org/downloads/ and run this again."
    echo
    read -r -p "Press Enter to close..."
    exit 1
fi

"$PYTHON" start.py "$@"
status=$?
if [ "$status" -ne 0 ]; then
    echo
    read -r -p "Something went wrong (exit $status). Press Enter to close..."
fi
