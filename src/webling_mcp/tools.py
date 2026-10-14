"""
Tool-Logik der 10 read-only Tools — von zwei Consumern genutzt:
- server.py registriert sie als FastMCP-Tools (stdio, Claude Code lokal)
- webling_chat.chat ruft sie in der Anthropic-Tool-Use-Schleife auf

Privacy-Muster unverändert: Antworten enthalten nur Pseudonyme/Aggregate.
"""

import logging
from datetime import datetime

from webling_mcp import domain, privacy
from webling_mcp.client import documents, members
from webling_mcp.rag import index as rag_index
from webling_mcp.rag import suche as rag_suche

logger = logging.getLogger(__name__)


def _sicher(fn):
    """Führt fn aus; Fehler werden als deutsche Meldung zurückgegeben, nie als Stacktrace."""
    try:
        return fn()
    except Exception as e:
        logger.error("Tool-Fehler: %s: %s", type(e).__name__, e)
        return {"fehler": f"Webling-Abfrage fehlgeschlagen ({type(e).__name__}): {e}"}


def baue_list_members(
    mitglieder: list[dict],
    mannschaft: str | None = None,
    geburtsjahr_von: int | None = None,
    geburtsjahr_bis: int | None = None,
) -> dict:
    """Gefilterte, pseudonymisierte Mitgliederliste."""
    gefiltert = domain.filtere_mitglieder(mitglieder, mannschaft, geburtsjahr_von, geburtsjahr_bis)
    return {
        "anzahl": len(gefiltert),
        "mitglieder": [privacy.pseudonymisiere(m) for m in gefiltert],
        # Bezieht sich auf die gefilterte Liste, nicht auf den Gesamtbestand:
        # das Modell rechnet mit dem, was es hier sieht.
        "datenqualitaet": {
            "beitrittsjahr": domain.datenabdeckung(gefiltert, domain.beitrittsjahr),
            "status": domain.datenabdeckung(gefiltert, domain.status_kategorie),
        },
    }


def baue_list_groups(mitglieder: list[dict]) -> dict:
    """Mannschaften mit Mitgliederzahl."""
    gruppen = domain.gruppiere_nach_mannschaft(mitglieder)
    return {
        "gruppen": [
            {"mannschaft": name, "mitglieder": len(spieler)}
            for name, spieler in sorted(gruppen.items())
        ]
    }


def baue_beitraege(mitglieder: list[dict], jahr: int) -> dict:
    """Mahnliste: Pseudonyme an das LLM, echte Namen in lokale Datei."""
    offen = domain.filtere_unbezahlt(mitglieder, jahr)
    zeilen = [
        f"- {m['vorname']} {m['name']} (bezahlt bis: {m['beitragsstatus'] or 'nie'})"
        for m in offen
    ]
    pfad = privacy.schreibe_namensliste("beitraege.md", f"Unbezahlte Beiträge {jahr}", zeilen)
    return {
        "jahr": jahr,
        "anzahl_offen": len(offen),
        "mitglieder": [privacy.pseudonym(m) for m in offen],
        "namensliste_lokal": pfad,
        "hinweis": "Echte Namen stehen nur in der lokalen Datei.",
    }


def baue_jubilaeen(mitglieder: list[dict], jahr: int) -> dict:
    """Jubilare (65, 70, 75, ...): Alter + Monat an das LLM, Namen lokal."""
    jubilare = domain.filtere_jubilaeen(mitglieder, jahr)
    # Genauer Tag NUR hier (lokale Datei) — in der LLM-Antwort wäre mit
    # alter + monat + tag das volle Geburtsdatum rekonstruierbar.
    zeilen = [
        f"- {m['vorname']} {m['name']} wird {m['alter']} "
        f"am {m['tag']:02d}.{m['monat']:02d}."
        for m in jubilare
    ]
    pfad = privacy.schreibe_namensliste("jubilaeen.md", f"Jubiläen {jahr}", zeilen)
    return {
        "jahr": jahr,
        "anzahl": len(jubilare),
        "jubilare": [
            {"id": privacy.pseudonym(m), "alter": m["alter"], "monat": m["monat"]}
            for m in jubilare
        ],
        "namensliste_lokal": pfad,
        "hinweis": "Echte Namen stehen nur in der lokalen Datei.",
    }


def baue_mannschaften(mitglieder: list[dict]) -> dict:
    """Aufstellungen: Pseudonym + Rang an das LLM, Namen lokal."""
    gruppen = domain.gruppiere_nach_mannschaft(mitglieder)
    zeilen = []
    for name, spieler in sorted(gruppen.items()):
        zeilen.append(f"## {name}")
        zeilen.extend(
            f"- Rang {s['rang'] if s['rang'] is not None else '-'}: {s['vorname']} {s['name']}"
            for s in spieler
        )
        zeilen.append("")
    pfad = privacy.schreibe_namensliste("mannschaften.md", "Mannschaften", zeilen)
    return {
        "mannschaften": {
            name: [{"id": privacy.pseudonym(s), "rang": s["rang"]} for s in spieler]
            for name, spieler in sorted(gruppen.items())
        },
        "namensliste_lokal": pfad,
        "hinweis": "Echte Namen stehen nur in der lokalen Datei.",
    }


def baue_statistik(mitglieder: list[dict]) -> dict:
    """Reines Aggregat — keine Namensdatei nötig."""
    return {"statistik": domain.statistik_nach_geburtsjahr(mitglieder)}


def baue_suche_dokumente(treffer: list[dict]) -> dict:
    """Suchtreffer (bereits maskiert, da der Index maskiert ist) + Hinweis."""
    return {
        "anzahl": len(treffer),
        "treffer": treffer,
        "hinweis": "Pseudonyme lokal auflösen: output/pseudonym_mapping.md",
    }


def baue_lies_dokument(dok: dict | None, dokument_id: int) -> dict:
    """Maskierter Volltext oder verständlicher Fehler."""
    if dok is None:
        return {"fehler": f"Dokument {dokument_id} ist nicht im Index."}
    return {**dok, "hinweis": "Pseudonyme lokal auflösen: output/pseudonym_mapping.md"}


# --- Tools ---------------------------------------------------------------

def list_members(
    mannschaft: str | None = None,
    geburtsjahr_von: int | None = None,
    geburtsjahr_bis: int | None = None,
) -> dict:
    """Listet Vereinsmitglieder (pseudonymisiert), optional gefiltert nach
    Mannschaft und Geburtsjahr-Bereich."""
    return _sicher(lambda: baue_list_members(
        members.hole_alle_mitglieder(), mannschaft, geburtsjahr_von, geburtsjahr_bis
    ))


def get_member(id: str) -> dict:
    """Ein Mitglied anhand seines Pseudonyms (z.B. 'M-1234'). Nur Whitelist-Felder."""
    def _lauf():
        mid = int(str(id).removeprefix("M-"))
        return privacy.pseudonymisiere(members.hole_mitglied(mid))
    return _sicher(_lauf)


def list_groups() -> dict:
    """Mannschaften/Gruppen mit Mitgliederzahl."""
    return _sicher(lambda: baue_list_groups(members.hole_alle_mitglieder()))


def list_documents(jahr: str | None = None) -> dict:
    """Dateinamen im Webling-Jahresordner (Default: aktuelles Jahr)."""
    def _lauf():
        j = jahr or str(datetime.now().year)
        ordner_id = documents.finde_jahresordner(j)
        if ordner_id is None:
            return {"fehler": f"Jahresordner '{j}' existiert nicht in Webling."}
        return {"jahr": j, "dokumente": documents.liste_dokumente(ordner_id)}
    return _sicher(_lauf)


def unbezahlte_beitraege(jahr: int | None = None) -> dict:
    """Mahnliste unbezahlter Beiträge. Pseudonyme an Claude, echte Namen
    in lokaler Datei (Pfad in der Antwort)."""
    return _sicher(lambda: baue_beitraege(
        members.hole_alle_mitglieder(), jahr or datetime.now().year
    ))


def jubilaeen(jahr: int | None = None) -> dict:
    """Mitglieder, die im Zieljahr 65, 70, 75, ... werden. Echte Namen
    in lokaler Datei (Pfad in der Antwort)."""
    return _sicher(lambda: baue_jubilaeen(
        members.hole_alle_mitglieder(), jahr or datetime.now().year
    ))


def mannschaften() -> dict:
    """Mannschaftsaufstellungen mit Rang. Echte Namen in lokaler Datei
    (Pfad in der Antwort)."""
    return _sicher(lambda: baue_mannschaften(members.hole_alle_mitglieder()))


def mitglieder_statistik() -> dict:
    """Mitgliederstatistik nach Geburtsjahr und Geschlecht (reines Aggregat)."""
    return _sicher(lambda: baue_statistik(members.hole_alle_mitglieder()))


KEIN_INDEX = ("Kein Suchindex gefunden — bitte zuerst "
              "'venv\\Scripts\\python scripts/ingest.py' ausführen.")


def suche_dokumente(frage: str, jahr: str | None = None, max_treffer: int = 5) -> dict:
    """Hybridsuche über die maskierten Vereinsdokumente (Satzung, Protokolle, ...).
    Treffer enthalten Pseudonyme statt Namen; Auflösung lokal über
    output/pseudonym_mapping.md."""
    def _lauf():
        if not rag_index.db_datei().exists():
            return {"fehler": KEIN_INDEX}
        return baue_suche_dokumente(rag_suche.suche(frage, jahr, max_treffer))
    return _sicher(_lauf)


def lies_dokument(dokument_id: int) -> dict:
    """Maskierter Volltext eines indexierten Dokuments (dokument_id aus suche_dokumente)."""
    def _lauf():
        if not rag_index.db_datei().exists():
            return {"fehler": KEIN_INDEX}
        return baue_lies_dokument(rag_suche.lies_volltext(dokument_id), dokument_id)
    return _sicher(_lauf)


# --- Anthropic-API-Anbindung (Phase C) ---------------------------------------

ANTHROPIC_TOOLS: list[dict] = [
    {"name": "list_members",
     "description": "Listet Vereinsmitglieder (pseudonymisiert), optional gefiltert "
                    "nach Mannschaft und Geburtsjahr-Bereich.",
     "input_schema": {"type": "object", "properties": {
         "mannschaft": {"type": "string"},
         "geburtsjahr_von": {"type": "integer"},
         "geburtsjahr_bis": {"type": "integer"}}, "required": []}},
    {"name": "get_member",
     "description": "Ein Mitglied anhand seines Pseudonyms (z.B. 'M-1234'). Nur Whitelist-Felder.",
     "input_schema": {"type": "object", "properties": {
         "id": {"type": "string", "description": "Pseudonym, z.B. 'M-1234'"}},
         "required": ["id"]}},
    {"name": "list_groups",
     "description": "Mannschaften/Gruppen mit Mitgliederzahl.",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "list_documents",
     "description": "Dateinamen im Webling-Jahresordner (Default: aktuelles Jahr).",
     "input_schema": {"type": "object", "properties": {
         "jahr": {"type": "string"}}, "required": []}},
    {"name": "unbezahlte_beitraege",
     "description": "Mahnliste unbezahlter Beiträge (Pseudonyme).",
     "input_schema": {"type": "object", "properties": {
         "jahr": {"type": "integer"}}, "required": []}},
    {"name": "jubilaeen",
     "description": "Mitglieder, die im Zieljahr 65, 70, 75, ... werden (Pseudonym, Alter, Monat).",
     "input_schema": {"type": "object", "properties": {
         "jahr": {"type": "integer"}}, "required": []}},
    {"name": "mannschaften",
     "description": "Mannschaftsaufstellungen mit Rang (Pseudonyme).",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "mitglieder_statistik",
     "description": "Mitgliederstatistik nach Geburtsjahr und Geschlecht (reines Aggregat).",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "suche_dokumente",
     "description": "Hybridsuche über die maskierten Vereinsdokumente (Satzung, Protokolle, ...).",
     "input_schema": {"type": "object", "properties": {
         "frage": {"type": "string"},
         "jahr": {"type": "string"},
         "max_treffer": {"type": "integer"}}, "required": ["frage"]}},
    {"name": "lies_dokument",
     "description": "Maskierter Volltext eines indexierten Dokuments (dokument_id aus suche_dokumente).",
     "input_schema": {"type": "object", "properties": {
         "dokument_id": {"type": "integer"}}, "required": ["dokument_id"]}},
]

WERKZEUGE = {
    "list_members": list_members, "get_member": get_member,
    "list_groups": list_groups, "list_documents": list_documents,
    "unbezahlte_beitraege": unbezahlte_beitraege, "jubilaeen": jubilaeen,
    "mannschaften": mannschaften, "mitglieder_statistik": mitglieder_statistik,
    "suche_dokumente": suche_dokumente, "lies_dokument": lies_dokument,
}


def fuehre_aus(name: str, argumente: dict) -> dict:
    """Führt ein Tool namens `name` mit `argumente` aus (für die Chat-Schleife)."""
    fn = WERKZEUGE.get(name)
    if fn is None:
        return {"fehler": f"Unbekanntes Tool: {name!r}"}
    return fn(**argumente)
