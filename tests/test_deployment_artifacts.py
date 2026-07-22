from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_production_compose_mounts_gcs_mirror_with_shared_group() -> None:
    compose = read("compose.yaml")
    production_env = read(".env.production.example")
    sync_script = read("deploy/scripts/sync_media.sh")

    assert "LOCAL_OBJECT_STORE_ROOT: /mnt/geoguesser" in compose
    assert "${GEOTRAINER_MEDIA_DIR:-/srv/geotrainer/media}:/mnt/geoguesser:ro" in compose
    assert "${GEOTRAINER_MEDIA_GID:-2000}" in compose
    assert "GEOTRAINER_MEDIA_BUCKET=gs://worldwide_images_geotrainer" in production_env
    assert "GEOTRAINER_MEDIA_GID=2000" in production_env
    assert 'chown -R "root:$GEOTRAINER_MEDIA_GID"' in sync_script
    assert 'find "$GEOTRAINER_MEDIA_DIR" -type f -exec chmod 0640' in sync_script


def test_vps_readiness_checks_gcs_sync_integrity_and_compose() -> None:
    script = read("deploy/scripts/check_vps_readiness.sh")

    assert 'gcloud storage ls "$GEOTRAINER_MEDIA_BUCKET/runtime-private/"' in script
    assert 'gcloud storage ls "$GEOTRAINER_MEDIA_BUCKET/source-private/"' in script
    assert "bash deploy/scripts/sync_media.sh" in script
    assert "bash deploy/scripts/verify_media_sync.sh" in script
    assert 'docker compose --env-file "$GEOTRAINER_ENV_FILE" config --quiet' in script
