from geoguesser import agent_factory


def test_factory_uses_official_deepagents_with_only_named_subagents(monkeypatch) -> None:
    captured = {}

    def fake_register(model, profile):
        captured["registered_model"] = model
        captured["profile"] = profile

    def fake_create(**kwargs):
        captured["create"] = kwargs
        return "compiled-agent"

    monkeypatch.setattr(agent_factory, "register_harness_profile", fake_register)
    monkeypatch.setattr(agent_factory, "create_deep_agent", fake_create)

    result = agent_factory.create_geoguesser_agent()

    assert result == "compiled-agent"
    assert captured["registered_model"] == agent_factory.FLASH_MODEL
    assert captured["profile"].general_purpose_subagent.enabled is False
    assert captured["profile"].excluded_middleware == frozenset({"SummarizationMiddleware"})
    assert captured["profile"].excluded_tools == frozenset(
        {"ls", "read_file", "write_file", "edit_file", "glob", "grep"}
    )
    assert [item["name"] for item in captured["create"]["subagents"]] == [
        "human-clue-specialist",
        "environmental-specialist",
    ]
    assert captured["create"]["response_format"] is agent_factory.CountryPrediction
