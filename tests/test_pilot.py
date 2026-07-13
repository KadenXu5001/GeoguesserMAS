from geoguesser.pilot import pilot_dataset_document


def test_pilot_has_representative_countries_and_45_slots() -> None:
    document = pilot_dataset_document()

    assert [country["iso2"] for country in document["countries"]] == ["FR", "TH", "BR"]
    assert document["targets"] == {
        "development_per_country": 10,
        "evaluation_per_country": 5,
        "total_panoramas": 45,
    }
    assert document["constraints"]["strict_replacement"] is True
    assert document["constraints"]["minimum_separation_meters"] == 10_000
