"""Anthropic-Tool-Definitionen und fuehre_aus (Phase C)."""
from webling_mcp import tools


def test_anthropic_tools_decken_alle_werkzeuge_ab():
    namen = {t["name"] for t in tools.ANTHROPIC_TOOLS}
    assert namen == set(tools.WERKZEUGE.keys())
    assert len(tools.ANTHROPIC_TOOLS) == 10
    for t in tools.ANTHROPIC_TOOLS:
        assert t["input_schema"]["type"] == "object"


def test_fuehre_aus_unbekanntes_tool():
    ergebnis = tools.fuehre_aus("gibts_nicht", {})
    assert "fehler" in ergebnis


def test_fuehre_aus_delegiert(monkeypatch):
    monkeypatch.setitem(tools.WERKZEUGE, "list_groups", lambda: {"gruppen": []})
    assert tools.fuehre_aus("list_groups", {}) == {"gruppen": []}
