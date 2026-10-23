from app.ai.bedrock import parse_json_reply


def test_plain_json():
    r = parse_json_reply('{"summary": "Drywall up.", "changes": ["drywall"], "concerns": []}')
    assert r == {"summary": "Drywall up.", "changes": ["drywall"], "concerns": []}


def test_fenced_json_with_prose():
    r = parse_json_reply('Here you go:\n```json\n{"summary": "Cabinets installed.", "changes": ["cabinets", ""]}\n```')
    assert r["summary"] == "Cabinets installed."
    assert r["changes"] == ["cabinets"]
    assert r["concerns"] == []


def test_non_json_falls_back_to_text():
    r = parse_json_reply("The wall was painted white.")
    assert r["summary"] == "The wall was painted white."


def test_bedrock_failure_falls_back_to_offline(monkeypatch):
    from app.ai import bedrock
    from app.config import settings

    def boom(*a, **k):
        raise RuntimeError("ValidationException: Operation not allowed")

    monkeypatch.setattr(settings, "ai_provider", "bedrock")
    monkeypatch.setattr(bedrock, "_converse", boom)
    img = (b"\x89PNG a", "image/png")
    result, model = bedrock.describe_progress(img, (b"\x89PNG b", "image/png"), "crew on site 8–4")
    assert model == "offline" and result["progress"] == "unknown"
    msg, model = bedrock.draft_checkin_message("Mike's Remodeling", "Kitchen renovation", "Tuesday")
    assert model == "offline" and msg.startswith("Hi Mike")
