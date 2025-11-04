#!/usr/bin/env bash
set -euo pipefail

# Refresh Python dependencies when requirements.txt exists and uv is available.
if [ -f requirements.txt ] && command -v uv >/dev/null 2>&1; then
    uv pip install --system -r requirements.txt
fi

# Add optional post-create customization commands here.
echo "post-create hook ready for custom steps."
