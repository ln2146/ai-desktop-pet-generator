from petgen.prompt import build_pet_prompt


def test_prompt_requires_description() -> None:
    try:
        build_pet_prompt(" ")
    except ValueError as exc:
        assert "description" in str(exc)
    else:
        raise AssertionError("empty description should fail")


def test_prompt_contains_action_layout() -> None:
    prompt = build_pet_prompt("cute coding cat")
    assert "cute coding cat" in prompt
    assert "Top row: 6 idle frames" in prompt
    assert "Middle row: 4 attentive hover frames" in prompt
    assert "Bottom row: 5 happy click frames" in prompt
    assert "#00FF00" in prompt
