#!/usr/bin/env bash
set -euo pipefail

: "${GEOTRAINER_DEPLOY_DIR:=$(pwd)}"
: "${GEOTRAINER_ENV_FILE:=/etc/geotrainer/production.env}"
: "${GEOTRAINER_MEDIA_DIR:=/srv/geotrainer/media}"
: "${GEOTRAINER_MEDIA_BUCKET:=gs://worldwide_images_geotrainer}"
: "${GEOTRAINER_MEDIA_GID:=2000}"

if [[ "$EUID" -ne 0 ]]; then
  echo "check_vps_readiness.sh must run as root" >&2
  exit 2
fi
for command in docker gcloud sha256sum; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "missing required command: $command" >&2
    exit 2
  fi
done
if [[ ! -r "$GEOTRAINER_ENV_FILE" ]]; then
  echo "production environment file is unreadable: $GEOTRAINER_ENV_FILE" >&2
  exit 2
fi
if [[ ! -f "$GEOTRAINER_DEPLOY_DIR/compose.yaml" ]]; then
  echo "compose.yaml is missing from deployment directory: $GEOTRAINER_DEPLOY_DIR" >&2
  exit 2
fi

cd "$GEOTRAINER_DEPLOY_DIR"
echo "Checking private GCS media access..."
gcloud storage ls "$GEOTRAINER_MEDIA_BUCKET/runtime-private/" >/dev/null
gcloud storage ls "$GEOTRAINER_MEDIA_BUCKET/source-private/" >/dev/null

echo "Synchronizing and validating the GCS-backed media mirror..."
export GEOTRAINER_MEDIA_DIR GEOTRAINER_MEDIA_BUCKET GEOTRAINER_MEDIA_GID
bash deploy/scripts/sync_media.sh
bash deploy/scripts/verify_media_sync.sh

echo "Validating the production Compose model..."
docker compose --env-file "$GEOTRAINER_ENV_FILE" config --quiet

echo "VPS readiness checks passed. Media is synchronized and Compose is valid."
