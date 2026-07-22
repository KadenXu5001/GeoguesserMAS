#!/usr/bin/env bash
set -euo pipefail

: "${GEOTRAINER_DEPLOY_DIR:=/srv/geotrainer/app}"
: "${GEOTRAINER_ENV_FILE:=/etc/geotrainer/production.env}"
: "${GEOTRAINER_BACKUP_PREFIX:=gs://worldwide_images_geotrainer/backups/mongodb}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="${GEOTRAINER_BACKUP_PREFIX}/geoguesser-${timestamp}.archive.gz"

cd "$GEOTRAINER_DEPLOY_DIR"
docker compose --env-file "$GEOTRAINER_ENV_FILE" exec -T mongodb sh -c \
  'mongodump --quiet --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --db "$MONGO_APP_DATABASE" --archive --gzip' \
  | gcloud storage cp - "$destination"

object_size="$(gcloud storage objects describe "$destination" --format='value(size)')"
if [[ ! "$object_size" =~ ^[0-9]+$ ]] || ((object_size == 0)); then
  echo "uploaded backup is missing or empty: $destination" >&2
  exit 1
fi

echo "MongoDB backup uploaded and verified: $destination ($object_size bytes)"
