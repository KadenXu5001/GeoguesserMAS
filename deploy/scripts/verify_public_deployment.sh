#!/usr/bin/env bash
set -euo pipefail

: "${GEOTRAINER_PUBLIC_URL:?Set GEOTRAINER_PUBLIC_URL to the production https:// URL}"
: "${GEOTRAINER_CURL_AUTH_CONFIG:=/etc/geotrainer/curl-auth.conf}"

if [[ "$GEOTRAINER_PUBLIC_URL" != https://* ]]; then
  echo "GEOTRAINER_PUBLIC_URL must use HTTPS" >&2
  exit 2
fi
if [[ ! -r "$GEOTRAINER_CURL_AUTH_CONFIG" ]]; then
  echo "authenticated curl config is unreadable: $GEOTRAINER_CURL_AUTH_CONFIG" >&2
  exit 2
fi

base_url="${GEOTRAINER_PUBLIC_URL%/}"
health_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  "$base_url/healthz")"
anonymous_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  "$base_url/")"
authenticated_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  --config "$GEOTRAINER_CURL_AUTH_CONFIG" "$base_url/")"

printf 'health=%s anonymous_app=%s authenticated_app=%s\n' \
  "$health_status" "$anonymous_status" "$authenticated_status"
[[ "$health_status" == "200" ]]
[[ "$anonymous_status" == "401" ]]
[[ "$authenticated_status" == "200" ]]

headers="$(curl --silent --show-error --head --config "$GEOTRAINER_CURL_AUTH_CONFIG" \
  "$base_url/")"
grep -Eiq '^strict-transport-security:' <<<"$headers"
grep -Eiq '^content-security-policy:' <<<"$headers"
grep -Eiq '^x-content-type-options:[[:space:]]*nosniff' <<<"$headers"
echo "public HTTPS and authentication smoke test passed"
