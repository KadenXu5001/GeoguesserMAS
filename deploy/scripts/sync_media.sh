#!/usr/bin/env bash
set -euo pipefail

: "${GEOTRAINER_MEDIA_DIR:=/srv/geotrainer/media}"
: "${GEOTRAINER_MEDIA_BUCKET:=gs://worldwide_images_geotrainer}"
: "${GEOTRAINER_MEDIA_GID:=2000}"

if [[ "$EUID" -ne 0 ]]; then
  echo "sync_media.sh must run as root so media ownership is deterministic" >&2
  exit 2
fi
if [[ "$GEOTRAINER_MEDIA_BUCKET" != gs://* ]]; then
  echo "GEOTRAINER_MEDIA_BUCKET must be a gs:// URI" >&2
  exit 2
fi
if [[ ! "$GEOTRAINER_MEDIA_GID" =~ ^[1-9][0-9]*$ ]]; then
  echo "GEOTRAINER_MEDIA_GID must be a positive numeric group ID" >&2
  exit 2
fi

install -d -o root -g "$GEOTRAINER_MEDIA_GID" -m 0750 \
  "$GEOTRAINER_MEDIA_DIR/runtime-private" \
  "$GEOTRAINER_MEDIA_DIR/source-private"
gcloud storage rsync --recursive \
  "$GEOTRAINER_MEDIA_BUCKET/runtime-private" \
  "$GEOTRAINER_MEDIA_DIR/runtime-private"
gcloud storage rsync --recursive \
  "$GEOTRAINER_MEDIA_BUCKET/source-private" \
  "$GEOTRAINER_MEDIA_DIR/source-private"
chown -R "root:$GEOTRAINER_MEDIA_GID" "$GEOTRAINER_MEDIA_DIR"
find "$GEOTRAINER_MEDIA_DIR" -type d -exec chmod 0750 {} +
find "$GEOTRAINER_MEDIA_DIR" -type f -exec chmod 0640 {} +
