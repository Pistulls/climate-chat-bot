#!/usr/bin/env bash
# Push the values in Infrastructure/secrets.local.env to their SSM SecureString parameters.
#
# - Values never appear in argv, shell history or this script's output. Each request is
#   written to a private (0600) temp file that is removed as soon as the call returns.
#   (AWS CLI v2 on macOS can't read --cli-input-json from file:///dev/stdin.)
#   Only parameter names are printed.
# - Placeholders (<...>) and empty values are skipped.
# - Works with macOS's bash 3.2 (no associative arrays).
#
# Usage: Infrastructure/scripts/put-secrets.sh [path/to/secrets.local.env]
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
file="${1:-$here/secrets.local.env}"
region="${AWS_REGION:-eu-west-2}"

if [[ ! -f "$file" ]]; then
  echo "No $file. Copy secrets.example.env to secrets.local.env and fill it in." >&2
  exit 1
fi

# KEY:parameter-name pairs.
params="
PROD_OPENROUTER_API_KEY:/climate-chat/prod/openrouter-api-key
PROD_TURNSTILE_SECRET_KEY:/climate-chat/prod/turnstile-secret-key
DEV_OPENROUTER_API_KEY:/climate-chat/dev/openrouter-api-key
INGEST_OPENROUTER_API_KEY:/climate-chat/ingest/openrouter-api-key
PROD_LOG_HASH_KEY:/climate-chat/prod/log-hash-key
DEV_LOG_HASH_KEY:/climate-chat/dev/log-hash-key
"

# Value of KEY from the file, read without sourcing it (so nothing in it is executed).
value_of() {
  local key="$1" line
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "${line%%=*}" == "$key" ]]; then
      printf '%s' "${line#*=}"
      return
    fi
  done < "$file"
}

# Private temp file for each request body; removed on any exit, including errors.
umask 077
request="$(mktemp "${TMPDIR:-/tmp}/put-secrets.XXXXXX")"
trap 'rm -f "$request"' EXIT

updated=0
for pair in $params; do
  key="${pair%%:*}"
  name="${pair#*:}"
  value="$(value_of "$key")"

  if [[ -z "$value" || "$value" == \<*\> ]]; then
    echo "skip   $name (not set)"
    continue
  fi

  NAME="$name" VALUE="$value" python3 -c '
import json, os
print(json.dumps({"Name": os.environ["NAME"], "Value": os.environ["VALUE"],
                  "Type": "SecureString", "Overwrite": True}))
' > "$request"
  aws ssm put-parameter --region "$region" --cli-input-json "file://$request" --output text >/dev/null
  : > "$request"

  echo "set    $name"
  updated=$((updated + 1))
done

echo "$updated parameter(s) updated."
