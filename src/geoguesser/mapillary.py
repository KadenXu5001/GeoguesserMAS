from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

import requests
from PIL import Image


GRAPH_URL = "https://graph.mapillary.com"
IMAGE_FIELDS = (
    "id,is_pano,computed_geometry,geometry,sequence,captured_at,width,height,"
    "thumb_original_url,quality_score"
)
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class DownloadedImage:
    path: Path
    sha256: str
    byte_count: int
    width: int
    height: int


class MapillaryClient:
    def __init__(
        self,
        token: str | None = None,
        *,
        session: requests.Session | None = None,
        attempts: int = 4,
    ) -> None:
        self.token = token or os.environ.get("MAPILLARY_ACCESS_TOKEN")
        if not self.token:
            raise RuntimeError("MAPILLARY_ACCESS_TOKEN is required")
        self.session = session or requests.Session()
        self.session.headers.update({"Authorization": f"OAuth {self.token}"})
        self.attempts = attempts

    def _get(self, url: str, **kwargs) -> requests.Response:
        for attempt in range(self.attempts):
            response = self.session.get(url, timeout=120, **kwargs)
            if response.status_code < 400:
                return response
            if response.status_code not in RETRYABLE_STATUS or attempt == self.attempts - 1:
                response.raise_for_status()
            retry_after = response.headers.get("Retry-After")
            time.sleep(float(retry_after) if retry_after else 2**attempt)
        raise AssertionError("retry loop exited unexpectedly")

    def get_image(self, image_id: str) -> dict[str, Any]:
        response = self._get(
            f"{GRAPH_URL}/{image_id}", params={"fields": IMAGE_FIELDS}
        )
        payload = response.json()
        if str(payload.get("id")) != str(image_id):
            raise RuntimeError("Mapillary returned an unexpected image id")
        return payload

    def iter_sequence_images(self, sequence_id: str) -> Iterator[dict[str, Any]]:
        url = f"{GRAPH_URL}/images"
        params: Mapping[str, Any] | None = {
            "sequence_ids": sequence_id,
            "is_pano": "true",
            "fields": IMAGE_FIELDS,
            "limit": 100,
        }
        while url:
            response = self._get(url, params=params)
            payload = response.json()
            yield from payload.get("data", [])
            url = payload.get("paging", {}).get("next")
            params = None

    def download_original(self, metadata: Mapping[str, Any], output_path: Path) -> DownloadedImage:
        image_url = metadata.get("thumb_original_url")
        if not image_url:
            raise ValueError("image metadata does not contain thumb_original_url")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = output_path.with_suffix(output_path.suffix + ".part")
        digest = hashlib.sha256()
        byte_count = 0
        try:
            with self._get(str(image_url), stream=True) as response:
                with temporary_path.open("wb") as destination:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        destination.write(chunk)
                        digest.update(chunk)
                        byte_count += len(chunk)
            with Image.open(temporary_path) as image:
                image.verify()
            with Image.open(temporary_path) as image:
                width, height = image.size
            if width < height or width / height < 1.5:
                raise ValueError("downloaded panorama does not have a plausible equirectangular aspect ratio")
            temporary_path.replace(output_path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return DownloadedImage(output_path, digest.hexdigest(), byte_count, width, height)
