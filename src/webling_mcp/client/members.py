"""
Webling-Mitglieder: Laden und Normalisieren.
Bulk-Abruf (eine Anfrage für viele IDs) mit Fallback auf Einzel-Abrufe.
Keine Daten werden persistiert — alles in-memory.
"""

import logging

import requests

from webling_mcp.client.http import get

logger = logging.getLogger(__name__)

# Webling Property-Namen (ermittelt aus GET /definition/member)
FELD_VORNAME = "Vorname"
FELD_NAME = "Name"
FELD_GEBURTSTAG = "Geburtstag"          # date, Format YYYY-MM-DD
FELD_BEITRITT = "Beitritt"              # date, Format YYYY-MM-DD (oft ungepflegt)
FELD_GESCHLECHT = "Geschlecht"          # enum: "w", "m"
FELD_MANNSCHAFT = "Mannschaft"          # enum: "Herren", "Damen", ...
FELD_RANG = "Rang"                      # int
FELD_BEITRAGSSTATUS = "Beitragsstatus"  # enum: "2025", "2026", ...
FELD_STATUS = "Status"                  # enum: "A-Mitglied", "P-Mitglied", ...

BULK_CHUNK = 100  # IDs pro Bulk-Anfrage


def hole_alle_mitglieder() -> list[dict]:
    """
    Lädt alle Mitglieder und gibt sie als normalisierte Dicts zurück.
    ACHTUNG: Interne, UNpseudonymisierte Darstellung — nie direkt an ein LLM.
    """
    ids = get("member").get("objects", [])
    mitglieder = []
    for start in range(0, len(ids), BULK_CHUNK):
        chunk = ids[start:start + BULK_CHUNK]
        for mid, roh in _hole_chunk(chunk):
            mitglieder.append(_normalisiere(mid, roh))
    logger.info("%d Mitglieder aus Webling geladen", len(mitglieder))
    return mitglieder


def hole_mitglied(mid: int) -> dict:
    """Lädt ein einzelnes Mitglied (normalisiert, unpseudonymisiert)."""
    return _normalisiere(mid, get(f"member/{mid}"))


def _hole_chunk(ids: list[int]) -> list[tuple[int, dict]]:
    """Bulk-Abruf mehrerer Mitglieder; Fallback auf Einzel-Abrufe."""
    if len(ids) == 1:
        return [(ids[0], get(f"member/{ids[0]}"))]
    try:
        daten = get("member/" + ",".join(str(i) for i in ids))
    except requests.HTTPError:
        logger.warning("Bulk-Abruf fehlgeschlagen, Fallback auf Einzel-Abrufe")
        return [(mid, get(f"member/{mid}")) for mid in ids]
    # Webling liefert bei mehreren IDs eine Liste in Anfrage-Reihenfolge
    if isinstance(daten, list) and len(daten) == len(ids):
        paare = list(zip(ids, daten))
        if all(_id_passt(mid, roh) for mid, roh in paare):
            return paare
        logger.warning("Bulk-Antwort-IDs passen nicht zur Anfrage, Fallback auf Einzel-Abrufe")
        return [(mid, get(f"member/{mid}")) for mid in ids]
    logger.warning("Unerwartetes Bulk-Format, Fallback auf Einzel-Abrufe")
    return [(mid, get(f"member/{mid}")) for mid in ids]


def _id_passt(mid: int, roh: dict) -> bool:
    """True, wenn die Antwort keine eigene ID trägt oder sie zur angefragten passt."""
    roh_id = roh.get("id")
    return roh_id is None or roh_id == mid


def _normalisiere(mid: int, roh: dict) -> dict:
    """Rohe Webling-Response -> interne Mitglieder-Darstellung."""
    props = roh.get("properties", {})
    # rang: Kontrakt ist int | None — Floats konvertieren, alles andere verwerfen
    rang_roh = props.get(FELD_RANG)
    rang = int(rang_roh) if isinstance(rang_roh, (int, float)) and not isinstance(rang_roh, bool) else None
    return {
        "id": mid,
        "vorname": props.get(FELD_VORNAME) or "",
        "name": props.get(FELD_NAME) or "",
        "geburtsdatum": props.get(FELD_GEBURTSTAG) or "",
        "beitrittsdatum": props.get(FELD_BEITRITT) or "",
        "geschlecht": (props.get(FELD_GESCHLECHT) or "").lower(),
        "mannschaft": props.get(FELD_MANNSCHAFT) or "",
        "rang": rang,
        "beitragsstatus": str(props.get(FELD_BEITRAGSSTATUS) or ""),
        "status": props.get(FELD_STATUS) or "",
    }
