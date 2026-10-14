"""Policy: Tool-Sichtbarkeit pro Rolle (Phase C)."""
from webling_chat import policy
from webling_mcp import tools


def test_vorstand_sieht_alle_tools():
    assert policy.erlaubte_tools("vorstand") == tools.ANTHROPIC_TOOLS


def test_unbekannte_rolle_sieht_nichts():
    assert policy.erlaubte_tools("gast") == []
