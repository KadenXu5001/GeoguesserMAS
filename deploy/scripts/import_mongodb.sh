#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 || "$1" != gs://* || ! "$2" =~ ^[0-9a-f]{64}$ ]]; then
  echo "usage: $0 gs://bucket/path/database.archive.gz expected_sha256" >&2
  exit 2
fi

: "${GEOTRAINER_DEPLOY_DIR:=/srv/geotrainer/app}"
: "${GEOTRAINER_ENV_FILE:=/etc/geotrainer/production.env}"
: "${MONGODB_DATABASE:=geoguesser}"
if [[ "${ALLOW_REPLACE_DATABASE:-}" != "$MONGODB_DATABASE" ]]; then
  echo "Set ALLOW_REPLACE_DATABASE=$MONGODB_DATABASE to confirm the production import." >&2
  exit 2
fi

archive_uri="$1"
expected_sha256="$2"
temp_dir="$(mktemp -d)"
archive_path="$temp_dir/database.archive.gz"
trap 'rm -rf -- "$temp_dir"' EXIT

gcloud storage cp "$archive_uri" "$archive_path"
printf '%s  %s\n' "$expected_sha256" "$archive_path" | sha256sum --check --status

cd "$GEOTRAINER_DEPLOY_DIR"
docker compose --env-file "$GEOTRAINER_ENV_FILE" stop app
docker compose --env-file "$GEOTRAINER_ENV_FILE" exec -T mongodb sh -c \
  'mongorestore --quiet --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --archive --gzip --drop --nsFrom "$MONGO_APP_DATABASE.*" --nsTo "$MONGO_APP_DATABASE.*"' \
  < "$archive_path"
docker compose --env-file "$GEOTRAINER_ENV_FILE" run --rm mongo-init-schema
docker compose --env-file "$GEOTRAINER_ENV_FILE" up -d app caddy
echo "MongoDB import completed; compare database_inventory.sh output with the source inventory."
