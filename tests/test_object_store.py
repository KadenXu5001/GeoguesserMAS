import hashlib

import pytest

from geoguesser.object_store import (
    RUNTIME_PRIVATE,
    LocalObjectStore,
    crc32c_base64,
    crc32c_update,
)


def test_crc32c_matches_standard_check_value() -> None:
    checksum = crc32c_update(0, b"123456789")
    chunked = crc32c_update(crc32c_update(0, b"1234"), b"56789")

    assert checksum == 0xE3069283
    assert chunked == checksum
    assert crc32c_base64(checksum) == "4waSgw=="


def test_local_object_store_uses_immutable_content_addressed_keys(tmp_path) -> None:
    source = tmp_path / "view.jpg"
    source.write_bytes(b"stable image bytes")
    store = LocalObjectStore(tmp_path / "store")

    first = store.put_file(source, namespace=RUNTIME_PRIVATE)
    second = store.put_file(source, namespace=RUNTIME_PRIVATE)

    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert first == second
    assert first.object_key == f"objects/{digest[:2]}/{digest}.jpg"
    assert first.path.read_bytes() == source.read_bytes()
    assert first.as_document()["path"] == first.path.as_posix()


@pytest.mark.parametrize(
    "object_key",
    ["../secret.jpg", "/absolute.jpg", "..\\secret.jpg"],
)
def test_local_object_store_rejects_unsafe_keys(tmp_path, object_key) -> None:
    with pytest.raises(ValueError, match="safe relative"):
        LocalObjectStore(tmp_path).path_for(RUNTIME_PRIVATE, object_key)


def test_local_object_store_detects_corrupt_existing_object(tmp_path) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"original")
    store = LocalObjectStore(tmp_path / "store")
    stored = store.put_file(source, namespace=RUNTIME_PRIVATE)
    stored.path.write_bytes(b"corrupt")

    with pytest.raises(RuntimeError, match="object is corrupt"):
        store.put_file(source, namespace=RUNTIME_PRIVATE)
