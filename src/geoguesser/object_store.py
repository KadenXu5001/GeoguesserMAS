from __future__ import annotations

import base64
import hashlib
import mimetypes
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Protocol


SOURCE_PRIVATE = "source-private"
RUNTIME_PRIVATE = "runtime-private"
ALLOWED_NAMESPACES = frozenset({SOURCE_PRIVATE, RUNTIME_PRIVATE})
DEFAULT_LOCAL_OBJECT_STORE_ROOT = Path(".local-data")
_CHUNK_SIZE = 1024 * 1024


def _crc32c_table() -> tuple[int, ...]:
    polynomial = 0x82F63B78
    table = []
    for value in range(256):
        checksum = value
        for _ in range(8):
            checksum = (checksum >> 1) ^ (
                polynomial if checksum & 1 else 0
            )
        table.append(checksum)
    return tuple(table)


_CRC32C_TABLE = _crc32c_table()


def crc32c_update(checksum: int, data: bytes) -> int:
    value = checksum ^ 0xFFFFFFFF
    for byte in data:
        value = _CRC32C_TABLE[(value ^ byte) & 0xFF] ^ (value >> 8)
    return value ^ 0xFFFFFFFF


def crc32c_base64(checksum: int) -> str:
    return base64.b64encode(checksum.to_bytes(4, "big")).decode("ascii")


@dataclass(frozen=True)
class StoredObject:
    storage_namespace: str
    country_iso2: str
    subdivision_code: str | None
    object_key: str
    path: Path
    sha256: str
    crc32c: str
    byte_count: int
    content_type: str

    def as_document(self) -> dict[str, object]:
        document = asdict(self)
        document["path"] = self.path.as_posix()
        if self.subdivision_code is None:
            document.pop("subdivision_code")
        return document


class ObjectStore(Protocol):
    def put_file(
        self,
        source_path: Path,
        *,
        namespace: str,
        country_iso2: str,
        subdivision_code: str | None = None,
        content_type: str | None = None,
    ) -> StoredObject: ...

    def path_for(self, namespace: str, object_key: str) -> Path: ...

    def staging_directory(self, *, prefix: str) -> tempfile.TemporaryDirectory[str]: ...


class LocalObjectStore:
    def __init__(self, root: Path = DEFAULT_LOCAL_OBJECT_STORE_ROOT) -> None:
        self.root = root

    @classmethod
    def from_environment(cls) -> LocalObjectStore:
        configured = os.environ.get("LOCAL_OBJECT_STORE_ROOT")
        return cls(Path(configured) if configured else DEFAULT_LOCAL_OBJECT_STORE_ROOT)

    def path_for(self, namespace: str, object_key: str) -> Path:
        if namespace not in ALLOWED_NAMESPACES:
            raise ValueError(f"unsupported object-store namespace: {namespace}")
        logical = PurePosixPath(object_key)
        if (
            logical.is_absolute()
            or not logical.parts
            or ".." in logical.parts
            or "\\" in object_key
        ):
            raise ValueError("object key must be a safe relative POSIX path")
        namespace_root = self.root / namespace
        candidate = namespace_root / Path(*logical.parts)
        if not candidate.resolve().is_relative_to(namespace_root.resolve()):
            raise ValueError("object key escapes its storage namespace")
        return candidate

    def staging_directory(self, *, prefix: str) -> tempfile.TemporaryDirectory[str]:
        staging_root = self.root / ".staging"
        staging_root.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(prefix=prefix, dir=staging_root)

    def put_file(
        self,
        source_path: Path,
        *,
        namespace: str,
        country_iso2: str,
        subdivision_code: str | None = None,
        content_type: str | None = None,
    ) -> StoredObject:
        if not source_path.is_file():
            raise FileNotFoundError(f"object-store source file not found: {source_path}")
        geography_prefix = self._geography_prefix(country_iso2, subdivision_code)
        digest, checksum, byte_count = self._checksums(source_path.open("rb"))
        suffix = source_path.suffix.lower()
        object_key = f"{geography_prefix}/objects/{digest[:2]}/{digest}{suffix}"
        destination = self.path_for(namespace, object_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            existing_digest, existing_crc32c, existing_size = self._checksums(
                destination.open("rb")
            )
            if (existing_digest, existing_crc32c, existing_size) != (
                digest,
                checksum,
                byte_count,
            ):
                raise RuntimeError(
                    f"content-addressed object is corrupt: {destination}"
                )
        else:
            temporary = destination.with_name(
                f".{destination.name}.{os.getpid()}.{uuid.uuid4().hex}.part"
            )
            try:
                with source_path.open("rb") as source, temporary.open("xb") as target:
                    shutil.copyfileobj(source, target, length=_CHUNK_SIZE)
                    target.flush()
                    os.fsync(target.fileno())
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        detected_type = content_type or mimetypes.guess_type(source_path.name)[0]
        return StoredObject(
            storage_namespace=namespace,
            country_iso2=country_iso2.upper(),
            subdivision_code=(subdivision_code.upper() if subdivision_code else None),
            object_key=object_key,
            path=destination,
            sha256=digest,
            crc32c=crc32c_base64(checksum),
            byte_count=byte_count,
            content_type=detected_type or "application/octet-stream",
        )

    @staticmethod
    def _geography_prefix(
        country_iso2: str,
        subdivision_code: str | None,
    ) -> str:
        country = country_iso2.upper()
        if not re.fullmatch(r"[A-Z]{2}", country):
            raise ValueError("object-store country must be an ISO2 code")
        prefix = f"countries/{country}"
        if subdivision_code is None:
            return prefix
        subdivision = subdivision_code.upper()
        if not re.fullmatch(r"[A-Z]{2}-[A-Z0-9]{1,3}", subdivision):
            raise ValueError("object-store subdivision must be an ISO 3166-2 code")
        if not subdivision.startswith(f"{country}-"):
            raise ValueError("object-store subdivision does not belong to country")
        return f"{prefix}/subregions/{subdivision}"

    @staticmethod
    def _checksums(source: BinaryIO) -> tuple[str, int, int]:
        sha256 = hashlib.sha256()
        crc32c = 0
        byte_count = 0
        try:
            for block in iter(lambda: source.read(_CHUNK_SIZE), b""):
                sha256.update(block)
                crc32c = crc32c_update(crc32c, block)
                byte_count += len(block)
        finally:
            source.close()
        return sha256.hexdigest(), crc32c, byte_count
