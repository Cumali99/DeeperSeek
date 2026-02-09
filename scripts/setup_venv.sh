#!/usr/bin/env bash
# Create .venv and install dependencies. Use when Python is from Homebrew (externally-managed).
# From repo root: bash scripts/setup_venv.sh

set -e
cd "$(dirname "$0")/.."

for py in python3.12 python3.11 python3.10 python3; do
  if command -v "$py" >/dev/null 2>&1; then
    minor=$("$py" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null) || continue
    if [[ "$minor" -ge 10 ]]; then
      echo "Using $py"
      "$py" -m venv .venv
      .venv/bin/pip install -r requirements.txt
      .venv/bin/pip install -e .
      echo "Done. Activate with: source .venv/bin/activate"
      exit 0
    fi
  fi
done
echo "Python 3.10+ required. Install: brew install python@3.12"
exit 1
