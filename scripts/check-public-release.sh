#!/usr/bin/env bash

set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

tracked_files="$(git ls-files)"

blocked_patterns=(
  '^\.deck_build/'
  '^deliverables/'
  '^docs/CLIENT_.*\.md$'
  '^PROGRESS\.md$'
  '^apps/dashboard/public/employees/'
  '^services/edge/data/'
  '\.(db|sqlite|sqlite3)$'
  '\.(pem|key|p12|pfx)$'
  '^services/edge/.*\.(pt|onnx)$'
)

for pattern in "${blocked_patterns[@]}"; do
  if printf '%s\n' "$tracked_files" | grep -Eq "$pattern"; then
    echo "Blocked public path matched: $pattern" >&2
    printf '%s\n' "$tracked_files" | grep -E "$pattern" >&2
    exit 1
  fi
done

tracked_env_files="$(printf '%s\n' "$tracked_files" | grep -E '(^|/)\.env($|\.)' | grep -vE '(^|/)\.env\.example$' || true)"
if [[ -n "$tracked_env_files" ]]; then
  echo "A non-example environment file is tracked:" >&2
  printf '%s\n' "$tracked_env_files" >&2
  exit 1
fi

while IFS= read -r -d '' path; do
  size="$(wc -c < "$path" | tr -d ' ')"
  if (( size > 25000000 )); then
    echo "Tracked file exceeds the 25 MB public-source limit: $path ($size bytes)" >&2
    exit 1
  fi
done < <(git ls-files -z)

secret_pattern='-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{20,}'
if git grep -nEI -e "$secret_pattern" -- . ':!bun.lock' ':!services/edge/uv.lock' ':!scripts/check-public-release.sh'; then
  echo "A value resembling a private key or access token was found." >&2
  exit 1
fi

personal_data_pattern='/Users/[^/[:space:]]+|OneDrive-Personal|/employees/[^"[:space:]]+\.(png|jpg|jpeg)'
if git grep -nEI -e "$personal_data_pattern" -- . ':!scripts/check-public-release.sh'; then
  echo "Personal demo data was found in public source." >&2
  exit 1
fi

echo "Public release audit passed: no blocked paths, oversized files, common secrets, or personal demo data detected."
