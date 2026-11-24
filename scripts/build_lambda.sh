#!/usr/bin/env bash
# Build the Lambda zip for the /api/chat service: build/lambda/climate-chat-api.zip
#
# - Runtime dependencies only (`uv export --no-default-groups`): no dev or ingest packages.
# - Wheels for the Lambda: Linux arm64 (manylinux 2.28), CPython 3.14, binary only.
# - The package without ingest/, plus a one-line handler.py at the zip root, because
#   Terraform's handler is "handler.handler" (Infrastructure/app/modules/hosting/lambda.tf).
#
# Usage: scripts/build_lambda.sh    (from anywhere; needs uv and zip)
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="$root/build/lambda"
pkg="$out/package"
zipfile="$out/climate-chat-api.zip"

rm -rf "$pkg" "$zipfile"
mkdir -p "$pkg"

uv export --project "$root" --frozen --no-default-groups --no-hashes --no-emit-project \
  --no-header --format requirements.txt > "$out/requirements.txt"

uv pip install --quiet \
  --target "$pkg" \
  --python-platform aarch64-manylinux_2_28 \
  --python-version 3.14 \
  --only-binary :all: \
  --requirement "$out/requirements.txt"

rsync -a --exclude '__pycache__' --exclude 'ingest/' "$root/src/climate_chat" "$pkg/"
printf 'from climate_chat.service import handler  # noqa: F401\n' > "$pkg/handler.py"

# Drop bytecode caches and test suites shipped inside wheels; they only add size.
find "$pkg" -type d \( -name '__pycache__' -o -name 'tests' \) -prune -exec rm -rf {} +

(cd "$pkg" && zip -q -r -X "$zipfile" .)
echo "Built $zipfile ($(du -h "$zipfile" | cut -f1))"
