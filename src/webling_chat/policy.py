"""
Policy: welche Tools sieht welche Rolle — die EINZIGE Stelle für diese
Entscheidung (gleiche Philosophie wie privacy.py). Heute trivial; spätere
Rollen (z.B. Jugendwart -> nur mannschaften + suche_dokumente) sind eine
Datenänderung in ROLLEN_TOOLS, kein Umbau.
"""

from webling_mcp import tools

# None = alle Tools; sonst Liste erlaubter Tool-Namen
ROLLEN_TOOLS: dict[str, list[str] | None] = {
    "vorstand": None,
}


def erlaubte_tools(rolle: str) -> list[dict]:
    if rolle not in ROLLEN_TOOLS:
        return []
    namen = ROLLEN_TOOLS[rolle]
    if namen is None:
        return tools.ANTHROPIC_TOOLS
    return [t for t in tools.ANTHROPIC_TOOLS if t["name"] in namen]
