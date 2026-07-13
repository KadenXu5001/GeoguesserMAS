from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PilotCountry:
    iso2: str
    country: str
    continent: str


PILOT_COUNTRIES = (
    PilotCountry("FR", "France", "Europe"),
    PilotCountry("TH", "Thailand", "Asia"),
    PilotCountry("BR", "Brazil", "South America"),
)

PILOT_VERSION = "pilot_v1"
DEVELOPMENT_PER_COUNTRY = 10
EVALUATION_PER_COUNTRY = 5
MINIMUM_SEPARATION_METERS = 10_000


def pilot_dataset_document() -> dict:
    return {
        "version": PILOT_VERSION,
        "kind": "pilot",
        "status": "draft",
        "countries": [asdict(country) for country in PILOT_COUNTRIES],
        "targets": {
            "development_per_country": DEVELOPMENT_PER_COUNTRY,
            "evaluation_per_country": EVALUATION_PER_COUNTRY,
            "total_panoramas": len(PILOT_COUNTRIES)
            * (DEVELOPMENT_PER_COUNTRY + EVALUATION_PER_COUNTRY),
        },
        "constraints": {
            "minimum_separation_meters": MINIMUM_SEPARATION_METERS,
            "strict_replacement": True,
            "sequence_isolated_splits": True,
            "ground_truth_method": "offline_boundaries",
        },
    }
