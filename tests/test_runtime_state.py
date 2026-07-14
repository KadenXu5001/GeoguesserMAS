from geoguesser.runtime_state import GeoState


def test_geo_state_preserves_deep_agents_structured_response() -> None:
    assert "structured_response" in GeoState.__annotations__
