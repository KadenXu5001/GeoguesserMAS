#!/usr/bin/env bash
set -euo pipefail

: "${GEOTRAINER_DEPLOY_DIR:=/srv/geotrainer/app}"
: "${GEOTRAINER_ENV_FILE:=/etc/geotrainer/production.env}"

cd "$GEOTRAINER_DEPLOY_DIR"
docker compose --env-file "$GEOTRAINER_ENV_FILE" exec -T mongodb sh -c \
  'mongosh --quiet --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --file /opt/geotrainer/inventory.js'
