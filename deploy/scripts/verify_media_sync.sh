#!/usr/bin/env bash
set -euo pipefail

: "${GEOTRAINER_MEDIA_DIR:=/srv/geotrainer/media}"
: "${GEOTRAINER_MEDIA_BUCKET:=gs://worldwide_images_geotrainer}"

failures=0
for namespace in runtime-private source-private; do
  local_root="$GEOTRAINER_MEDIA_DIR/$namespace"
  if [[ ! -d "$local_root" ]]; then
    echo "missing local media namespace: $local_root" >&2
    failures=$((failures + 1))
    continue
  fi

  local_count="$(find "$local_root" -type f | wc -l | tr -d ' ')"
  cloud_count="$(
    gcloud storage ls --recursive "$GEOTRAINER_MEDIA_BUCKET/$namespace" \
      | awk '/^gs:\/\// && !/:$/ && !/\/$/ {count += 1} END {print count + 0}'
  )"
  echo "$namespace files: local=$local_count cloud=$cloud_count"
  if [[ "$local_count" != "$cloud_count" ]]; then
    echo "media count mismatch for $namespace" >&2
    failures=$((failures + 1))
  fi

  while IFS= read -r -d '' object; do
    filename="$(basename "$object")"
    expected_sha256="${filename%%.*}"
    if [[ ! "$expected_sha256" =~ ^[0-9a-f]{64}$ ]]; then
      echo "unexpected non-content-addressed media file: $object" >&2
      failures=$((failures + 1))
      continue
    fi
    actual_sha256="$(sha256sum "$object" | awk '{print $1}')"
    if [[ "$actual_sha256" != "$expected_sha256" ]]; then
      echo "media checksum mismatch: $object" >&2
      failures=$((failures + 1))
    fi
  done < <(find "$local_root" -type f -print0)
done

if ((failures > 0)); then
  echo "media verification failed with $failures error(s)" >&2
  exit 1
fi
echo "media verification passed"
