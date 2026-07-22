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
    assert "cpus: 1.0" in compose
    assert 'REQUIRE_PROXY_AUTH: "false"' in compose
    assert "basic_auth" not in read("deploy/Caddyfile")
    assert "APP_BASIC_AUTH" not in production_env
    assert "GEOTRAINER_MEDIA_BUCKET=gs://worldwide_images_geotrainer" in production_env
    assert "GEOTRAINER_MEDIA_GID=2000" in production_env
    assert 'chown -R "root:$GEOTRAINER_MEDIA_GID"' in sync_script
    assert 'find "$GEOTRAINER_MEDIA_DIR" -type f -exec chmod 0640' in sync_script


def test_vps_readiness_checks_gcs_sync_integrity_and_compose() -> None:
    script = read("deploy/scripts/check_vps_readiness.sh")
    verifier = read("deploy/scripts/verify_media_sync.sh")

    assert 'gcloud storage ls "$GEOTRAINER_MEDIA_BUCKET/runtime-private/"' in script
    assert 'gcloud storage ls "$GEOTRAINER_MEDIA_BUCKET/source-private/"' in script
    assert "bash deploy/scripts/sync_media.sh" in script
    assert "bash deploy/scripts/verify_media_sync.sh" in script
    assert 'docker compose --env-file "$GEOTRAINER_ENV_FILE" config --quiet' in script
    assert "!/:$/" in verifier


def test_github_deployment_is_serialized_tested_and_fail_closed() -> None:
    workflow = read(".github/workflows/deploy-production.yml")
    deploy_script = read("deploy/scripts/deploy_release.sh")

    assert "branches: [main]" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "needs: test" in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert "git status --porcelain" in workflow
    assert "git merge --ff-only" in workflow
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in workflow
    assert workflow.index("schema_paths=(") < workflow.index("git merge --ff-only")
    assert "MongoDB schema-sensitive files changed" in deploy_script
    assert "verify_public_deployment.sh" in deploy_script
