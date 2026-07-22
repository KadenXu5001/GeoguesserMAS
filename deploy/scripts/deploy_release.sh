#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 || ! "$1" =~ ^[0-9a-f]{40}$ || ! "$2" =~ ^[0-9a-f]{40}$ ]]; then
  echo "usage: $0 DEPLOY_REVISION PREVIOUS_REVISION" >&2
  exit 2
fi

revision="$1"
previous_revision="$2"
: "${GEOTRAINER_DEPLOY_DIR:=/srv/geotrainer/app}"
: "${GEOTRAINER_ENV_FILE:=/etc/geotrainer/production.env}"
: "${GEOTRAINER_PUBLIC_URL:=https://geo-trainer.com}"

cd "$GEOTRAINER_DEPLOY_DIR"
[[ "$(git rev-parse HEAD)" == "$revision" ]] || {
  echo "deployment checkout does not match requested revision" >&2
  exit 1
}
[[ -r "$GEOTRAINER_ENV_FILE" ]] || {
  echo "production environment file is unreadable: $GEOTRAINER_ENV_FILE" >&2
  exit 1
}

schema_paths=(src/geoguesser/storage.py deploy/mongodb/init-app-user.js)
if ! git diff --quiet "$previous_revision" "$revision" -- "${schema_paths[@]}"; then
  echo "MongoDB schema-sensitive files changed; take a verified backup and deploy manually." >&2
  exit 1
fi

docker compose --env-file "$GEOTRAINER_ENV_FILE" config --quiet
docker compose --env-file "$GEOTRAINER_ENV_FILE" up -d --build --remove-orphans

for attempt in $(seq 1 30); do
  if curl --fail --silent --show-error "$GEOTRAINER_PUBLIC_URL/healthz" >/dev/null; then
    GEOTRAINER_PUBLIC_URL="$GEOTRAINER_PUBLIC_URL" \
      bash deploy/scripts/verify_public_deployment.sh
    docker compose --env-file "$GEOTRAINER_ENV_FILE" ps
    echo "deployed revision $revision"
    exit 0
  fi
  sleep 2
done

echo "production health check did not pass within 60 seconds" >&2
docker compose --env-file "$GEOTRAINER_ENV_FILE" ps >&2
docker compose --env-file "$GEOTRAINER_ENV_FILE" logs --no-color --tail=100 app caddy >&2
exit 1
