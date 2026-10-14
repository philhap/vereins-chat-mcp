"""
Privacy-Schicht: Die EINZIGE Stelle, die entscheidet, welche Felder ein
LLM sieht (Whitelist), plus lokales Rendern von Namenslisten.

DSGVO-Design (siehe Spec):
- Tool-Responses: pseudonymisiert (Stufe 2) -> Claude API zulässig
- Echte Namen: nur in lokalen Dateien unter output/ (Stufe 3, verlässt
  den Rechner nicht)
"""

import os
from pathlib import Path

from webling_mcp.domain import beitrittsjahr, geburtsjahr, mitgliedsbeitrag

# Ausgabeverzeichnis: per Env-Variable übersteuerbar (z.B. bei Nicht-Editable-Install);
# Default: <Repo-Root>/output (gilt für die Editable-Installation dieses Projekts)
OUTPUT_DIR = Path(
    os.environ.get("WEBLING_MCP_OUTPUT_DIR")
    or Path(__file__).resolve().parents[2] / "output"
)

# Feste Ausgabedateien — die EINZIGEN Orte, an die Klarnamen geschrieben werden
ERLAUBTE_DATEINAMEN = {"beitraege.md", "jubilaeen.md", "mannschaften.md",
                       "pseudonym_mapping.md", "pii_stichprobe.md",
                       "status_pruefung.md"}


def pseudonym(mitglied: dict) -> str:
    """Stabiles Pseudonym aus der Webling-Mitglieds-ID (keine Mapping-Tabelle nötig)."""
    return f"M-{int(mitglied['id'])}"


def pseudonymisiere(mitglied: dict) -> dict:
    """
    Baut die LLM-sichere Darstellung eines Mitglieds AUF (konstruktive
    Whitelist). Name, Vorname, E-Mail, Adresse, Telefon und die vollen
    Datumsangaben (Geburtstag, Beitritt) existieren in der Ausgabe nicht —
    von Datumsfeldern geht ausschließlich das Jahr heraus.
    """
    return {
        "id": pseudonym(mitglied),
        "geburtsjahr": geburtsjahr(mitglied),
        "beitrittsjahr": beitrittsjahr(mitglied),
        "geschlecht": mitglied.get("geschlecht", ""),
        "mannschaft": mitglied.get("mannschaft", ""),
        "rang": mitglied.get("rang"),
        "beitragsstatus": mitglied.get("beitragsstatus", ""),
        "status": mitglied.get("status", ""),
        "mitgliedsbeitrag": mitgliedsbeitrag(mitglied),
    }


def schreibe_namensliste(dateiname: str, titel: str, zeilen: list[str]) -> str:
    """
    Schreibt eine aufgelöste Liste mit echten Namen als lokale Markdown-Datei.
    Fester Dateiname pro Tool — wird überschrieben, keine Ansammlung alter
    PII-Dateien. Gibt den absoluten Pfad für die Tool-Response zurück.

    Konstruktive Dateinamen-Whitelist: verhindert Path-Traversal und Schreiben
    von Klarnamen außerhalb des gitignorierten output/-Verzeichnisses.
    """
    if dateiname not in ERLAUBTE_DATEINAMEN:
        raise ValueError(f"Unbekannter Ausgabe-Dateiname: {dateiname!r}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pfad = OUTPUT_DIR / dateiname
    inhalt = f"# {titel}\n\n" + "\n".join(zeilen) + "\n"
    pfad.write_text(inhalt, encoding="utf-8")
    return str(pfad)
