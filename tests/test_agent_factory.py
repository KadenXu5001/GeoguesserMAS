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
        "urban-specialist",
        "rural-specialist",
    ]
    assert len(captured["create"]["middleware"]) == 1
    assert captured["create"]["middleware"][0].__class__.__name__ == "BudgetMiddleware"
    assert "response_format" not in captured["create"]
    assert captured["create"]["state_schema"] is agent_factory.GeoState


def test_single_agent_ablation_has_no_subagents(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(agent_factory, "register_harness_profile", lambda *args: None)
    monkeypatch.setattr(agent_factory, "create_deep_agent", lambda **kwargs: captured.update(kwargs) or "ablation")

    assert agent_factory.create_single_agent_ablation() == "ablation"
    assert "subagents" not in captured
