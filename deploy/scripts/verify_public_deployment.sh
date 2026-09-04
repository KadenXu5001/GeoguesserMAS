#!/usr/bin/env bash
set -euo pipefail

: "${GEOTRAINER_PUBLIC_URL:?Set GEOTRAINER_PUBLIC_URL to the production https:// URL}"

if [[ "$GEOTRAINER_PUBLIC_URL" != https://* ]]; then
  echo "GEOTRAINER_PUBLIC_URL must use HTTPS" >&2
  exit 2
fi

base_url="${GEOTRAINER_PUBLIC_URL%/}"
health_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  "$base_url/healthz")"
app_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  "$base_url/")"

printf 'health=%s public_app=%s\n' "$health_status" "$app_status"
[[ "$health_status" == "200" ]]
[[ "$app_status" == "200" ]]

headers="$(curl --silent --show-error --head "$base_url/")"
grep -Eiq '^strict-transport-security:' <<<"$headers"
grep -Eiq '^content-security-policy:' <<<"$headers"
grep -Eiq '^x-content-type-options:[[:space:]]*nosniff' <<<"$headers"
echo "public HTTPS smoke test passed"
