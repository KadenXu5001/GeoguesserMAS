#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || "$1" != gs://* ]]; then
  echo "usage: $0 gs://bucket/backups/mongodb/backup.archive.gz" >&2
  exit 2
fi

: "${GEOTRAINER_DEPLOY_DIR:=/srv/geotrainer/app}"
: "${GEOTRAINER_ENV_FILE:=/etc/geotrainer/production.env}"
readonly restore_database="geoguesser_restore_drill"

cd "$GEOTRAINER_DEPLOY_DIR"
gcloud storage cat "$1" | docker compose --env-file "$GEOTRAINER_ENV_FILE" exec -T mongodb sh -c \
  'mongorestore --quiet --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --archive --gzip --drop --nsFrom "$MONGO_APP_DATABASE.*" --nsTo "geoguesser_restore_drill.*"'

docker compose --env-file "$GEOTRAINER_ENV_FILE" exec -T mongodb sh -c \
  'RESTORE_DRILL_DATABASE=geoguesser_restore_drill mongosh --quiet --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --file /opt/geotrainer/verify-restore.js'

if [[ "${CLEANUP_RESTORE_DRILL:-false}" == "true" ]]; then
  docker compose --env-file "$GEOTRAINER_ENV_FILE" exec -T mongodb sh -c \
    'mongosh --quiet --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "db.getSiblingDB(\"geoguesser_restore_drill\").dropDatabase()"'
fi

echo "restore drill counts and representative records match"
