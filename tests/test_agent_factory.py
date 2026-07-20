from geoguesser import agent_factory


def test_factory_uses_official_deepagents_with_only_named_subagents(monkeypatch) -> None:
    captured = {}

    def fake_register(model, profile):
        captured["registered_model"] = model
        captured["profile"] = profile

    def fake_create(**kwargs):
        captured["create"] = kwargs
        return "compiled-agent"

    def fake_create_specialist(**kwargs):
        captured.setdefault("specialists", []).append(kwargs)
        return "compiled-specialist"

    monkeypatch.setattr(agent_factory, "register_harness_profile", fake_register)
    monkeypatch.setattr(agent_factory, "create_deep_agent", fake_create)
    monkeypatch.setattr(agent_factory, "create_agent", fake_create_specialist)

    result = agent_factory.create_geoguesser_agent()

    assert result == "compiled-agent"
    assert captured["registered_model"] == agent_factory.FLASH_MODEL
    assert captured["profile"].general_purpose_subagent.enabled is False
    assert captured["profile"].excluded_middleware == frozenset(
        {"SummarizationMiddleware", "TodoListMiddleware"}
    )
    assert captured["profile"].excluded_tools == frozenset(
        {"ls", "read_file", "write_file", "edit_file", "glob", "grep"}
    )
    assert [item["name"] for item in captured["create"]["subagents"]] == [
        "urban-specialist",
        "rural-specialist",
    ]
    assert all("middleware" not in item for item in captured["specialists"])
    assert [item.__class__.__name__ for item in captured["create"]["middleware"]] == [
        "MASTodoListMiddleware",
        "BudgetMiddleware",
    ]
    assert "response_format" not in captured["create"]
    assert captured["create"]["state_schema"] is agent_factory.GeoState


def test_single_agent_ablation_has_no_subagents(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(agent_factory, "register_harness_profile", lambda *args: None)
    monkeypatch.setattr(agent_factory, "create_deep_agent", lambda **kwargs: captured.update(kwargs) or "ablation")

    assert agent_factory.create_single_agent_ablation() == "ablation"
    assert "subagents" not in captured


def test_supervisor_prompt_names_exact_todo_and_tool_order() -> None:
    prompt = agent_factory.ORCHESTRATOR_PROMPT
    expected = [
        "write_todos",
        "Extract visual evidence with extract_visual_evidence",
        "Delegate to urban-specialist or rural-specialist with task",
        "Optionally reexamine_region only for two close country signals",
        "Emit final country prediction with emit_prediction",
    ]

    assert all(value in prompt for value in expected)
    assert prompt.index("Immediately call the exact tool named `extract_visual_evidence`") < prompt.index(
        "delegate using the exact tool name `task`"
    ) < prompt.index("Re-examination is temporarily disabled") < prompt.index(
        "calling the exact tool `emit_prediction`"
    )


def test_mas_todo_guidance_forbids_rewriting_the_plan() -> None:
    middleware = agent_factory.MASTodoListMiddleware()

    assert "byte-for-byte identical" in middleware.system_prompt
    assert "Never rename, add, remove, reorder" in middleware.system_prompt
    assert "Never add, delete, rename, reorder" in middleware.tool_description
