"""
Webling-Dokumente: Jahresordner finden und Dokumente auflisten (read-only).
Dateinamen gelten als unkritisch (keine PII) — siehe Spec.
"""

import logging
import re
from datetime import datetime

from webling_mcp.client.http import get, get_bytes

logger = logging.getLogger(__name__)


def finde_jahresordner(jahr: str | None = None) -> int | None:
    """Sucht die Dokumentgruppen-ID für den Jahresordner (z.B. '2026')."""
    if jahr is None:
        jahr = str(datetime.now().year)
    gruppen_ids = get("documentgroup").get("objects", [])
    for gid in gruppen_ids:
        gruppe = get(f"documentgroup/{gid}")
        if gruppe.get("properties", {}).get("title") == jahr:
            return gid
    return None


def liste_dokumente(ordner_id: int) -> list[dict]:
    """Listet Dokumente eines Ordners: {id, title, name, size}."""
    gruppe = get(f"documentgroup/{ordner_id}")
    doc_ids = gruppe.get("children", {}).get("document", [])
    dokumente = []
    for did in doc_ids:
        doc = get(f"document/{did}")
        props = doc.get("properties", {})
        file_info = props.get("file") or {}
        dokumente.append({
            "id": did,
            "title": props.get("title", ""),
            "name": file_info.get("name", ""),
            "size": file_info.get("size", 0),
        })
    return dokumente


def lade_dokument(dokument_id: int) -> bytes:
    """Lädt den Dateiinhalt eines Dokuments.

    Webling stellt Downloads NICHT über 'document/<id>/download' bereit (404 im
    Live-Check) — der tatsächliche Dateipfad steht im href-Feld der
    Dokument-Metadaten (properties.file.href), inkl. URL-kodiertem Dateinamen.
    """
    doc = get(f"document/{dokument_id}")
    props = doc.get("properties", {}) or {}
    file_info = props.get("file") or {}
    href = file_info.get("href", "")
    if not href:
        raise ValueError(f"Kein Datei-href für Dokument {dokument_id} gefunden.")
    return get_bytes(href)


def alle_jahresordner() -> list[tuple[str, int]]:
    """Alle Jahresordner (Titel = vierstellige Jahreszahl) als (jahr, id), sortiert."""
    ordner = []
    for gid in get("documentgroup").get("objects", []):
        titel = str(get(f"documentgroup/{gid}").get("properties", {}).get("title", ""))
        if re.fullmatch(r"(19|20)\d{2}", titel):
            ordner.append((titel, gid))
    return sorted(ordner)


def alle_dokumentordner() -> list[tuple[str, int]]:
    """ALLE Dokumentordner als (titel, id), sortiert — auch Nicht-Jahres-Ordner
    wie 'Satzungen' oder 'Öffentliche Daten' (der Ingest indexiert alles)."""
    ordner = []
    for gid in get("documentgroup").get("objects", []):
        titel = str(get(f"documentgroup/{gid}").get("properties", {}).get("title", ""))
        ordner.append((titel, gid))
    return sorted(ordner)
