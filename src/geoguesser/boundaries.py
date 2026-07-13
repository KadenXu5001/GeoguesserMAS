from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import requests
import shapefile
from shapely.geometry import Point, shape
from shapely.prepared import prep


NATURAL_EARTH_VERSION = "5.1.1"
NATURAL_EARTH_URL = (
    "https://naturalearth.s3.amazonaws.com/5.1.1/10m_cultural/"
    "ne_10m_admin_0_countries.zip"
)
DEFAULT_BOUNDARY_DIR = Path("data/boundaries/natural-earth-5.1.1")
DEFAULT_SHAPEFILE = DEFAULT_BOUNDARY_DIR / "ne_10m_admin_0_countries.shp"


def download_natural_earth(
    output_dir: Path = DEFAULT_BOUNDARY_DIR,
    *,
    session: requests.Session | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / "ne_10m_admin_0_countries.zip"
    client = session or requests.Session()
    with client.get(NATURAL_EARTH_URL, stream=True, timeout=120) as response:
        response.raise_for_status()
        with archive.open("wb") as destination:
            shutil.copyfileobj(response.raw, destination)
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.namelist()
        if not members or any(Path(member).is_absolute() or ".." in Path(member).parts for member in members):
            raise ValueError("Natural Earth archive contains an unsafe path")
        bundle.extractall(output_dir)
    archive.unlink()
    shapefile_path = output_dir / "ne_10m_admin_0_countries.shp"
    if not shapefile_path.exists():
        raise RuntimeError("Natural Earth archive did not contain the expected shapefile")
    return shapefile_path


class CountryBoundaries:
    def __init__(self, shapefile_path: Path = DEFAULT_SHAPEFILE) -> None:
        if not shapefile_path.exists():
            raise FileNotFoundError(
                f"boundary file not found: {shapefile_path}; run download-boundaries first"
            )
        reader = shapefile.Reader(str(shapefile_path), encoding="utf-8")
        field_names = [field[0] for field in reader.fields[1:]]
        self.dataset_id = f"natural-earth-{NATURAL_EARTH_VERSION}-10m-admin0-countries"
        self._countries = []
        for item in reader.iterShapeRecords():
            properties = dict(zip(field_names, item.record))
            iso2 = properties.get("ISO_A2_EH") or properties.get("ISO_A2")
            if not iso2 or iso2 == "-99":
                continue
            geometry = shape(item.shape.__geo_interface__)
            self._countries.append((str(iso2).strip().upper(), prep(geometry)))

    def country_iso2(self, latitude: float, longitude: float) -> str | None:
        point = Point(longitude, latitude)
        for iso2, geometry in self._countries:
            if geometry.covers(point):
                return iso2
        return None
