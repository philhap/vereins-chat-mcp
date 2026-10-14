"""
Inkrementeller Ingest: Webling-Dokumente -> Extraktion -> Maskierung ->
Chunking/Embeddings -> lokaler Index. Manuell anzustoßen (scripts/ingest.py).

Einziger Teil von Phase B mit Webling-Zugriff. Rohdaten werden nur im
Speicher gehalten; auf die Platte gelangt ausschließlich maskierter Text.
Das Pseudonym-Mapping (Klarnamen!) geht über privacy.schreibe_namensliste
nach output/ und wird über Läufe hinweg gemerged (Pseudonyme sind stabil).
"""

import logging
import re
from datetime import datetime

from webling_mcp import privacy
from webling_mcp.client import documents, members
from webling_mcp.rag import embeddings, index
from webling_mcp.rag.extraktion import extrahiere_text
from webling_mcp.rag.maskierung import Maskierer, _lade_nlp

logger = logging.getLogger(__name__)

REGEX_MAPPING_ZEILE = re.compile(r"^- (\S+) = (.+)$")


def _nlp_fuer_ingest():
    """Indirektion, damit Tests das NER-Modell ersetzen können."""
    return _lade_nlp()


def _jetzt() -> str:
    """Indirektion, damit Tests die Uhr ersetzen können."""
    return datetime.now().isoformat(timespec="seconds")


def lade_pseudonym_mapping() -> dict[str, str]:
    """Bisheriges Pseudonym-Mapping aus output/ einlesen (für den Merge).

    Wird auch von webling_chat für die Rücksubstitution genutzt.
    """
    pfad = privacy.OUTPUT_DIR / "pseudonym_mapping.md"
    if not pfad.exists():
        return {}
    mapping = {}
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        m = REGEX_MAPPING_ZEILE.match(zeile)
        if m:
            mapping[m.group(1)] = m.group(2)
    return mapping


# Alias für Bestandscode/-tests
_lade_bestehendes_mapping = lade_pseudonym_mapping


def synchronisiere() -> dict:
    """Gleicht den Index mit Webling ab; gibt eine Zusammenfassung zurück."""
    mitglieder = members.hole_alle_mitglieder()
    mapping_gesamt = lade_pseudonym_mapping()
    # Fremd-Namen aus früheren Läufen als bekannte Namensliste seeden —
    # die NER erkennt denselben Namen nicht in jedem Dokument.
    bekannte_fremde = {name for pseudo, name in mapping_gesamt.items()
                       if pseudo.startswith("P-")}
    masker = Maskierer(mitglieder, nlp=_nlp_fuer_ingest(),
                       bekannte_fremde=bekannte_fremde)
    con = index.oeffne_db()

    vorhandene = index.indexierte_dokumente(con)
    gesehen: set[int] = set()
    zusammenfassung = {"neu": 0, "unveraendert": 0, "entfernt": 0,
                       "nachmaskiert": 0, "uebersprungen": [], "fehler": [],
                       "mapping_datei": None}

    # Pass 1: laden + extrahieren + NER-Vorab-Pass. Erst wenn alle Fremd-Namen
    # des Laufs bekannt sind, wird maskiert — sonst leakt ein Name in Dokument B,
    # den die NER nur in Dokument A erkannt hat.
    zu_indexieren: list[tuple[str, dict, str]] = []
    for jahr, ordner_id in documents.alle_dokumentordner():
        for doku in documents.liste_dokumente(ordner_id):
            if doku["id"] in gesehen:
                continue  # Dokument hängt in mehreren Ordnern
            gesehen.add(doku["id"])
            if vorhandene.get(doku["id"]) == doku["size"]:
                zusammenfassung["unveraendert"] += 1
                continue
            # Einzelfehler (z.B. Rate-Limit, Verbindungsabbruch) dürfen den Lauf
            # nicht abbrechen — das Dokument fehlt dann im Index und wird beim
            # nächsten Ingest erneut versucht (Größenabgleich schlägt fehl).
            try:
                daten = documents.lade_dokument(doku["id"])
            except Exception as e:
                logger.warning("Download fehlgeschlagen (%s): %s",
                               doku["name"], type(e).__name__)
                zusammenfassung["fehler"].append(doku["name"])
                continue
            text = extrahiere_text(doku["name"], daten)
            if text is None:
                zusammenfassung["uebersprungen"].append(doku["name"])
                continue
            masker.erkenne_fremde(text)
            zu_indexieren.append((jahr, doku, text))

    # Pass 2: maskieren + indexieren
    for jahr, doku, text in zu_indexieren:
        maskiert, mapping = masker.maskiere(text, dokument_id=doku["id"])
        mapping_gesamt.update(mapping)
        chunks = index.chunke(maskiert)
        vektoren = embeddings.embed_passagen(chunks)
        index.speichere_dokument(con, {
            "id": doku["id"], "titel": doku["title"], "dateiname": doku["name"],
            "jahr": jahr, "groesse": doku["size"], "volltext": maskiert,
        }, chunks, vektoren)
        zusammenfassung["neu"] += 1

    for dokument_id in set(vorhandene) - gesehen:
        index.loesche_dokument(con, dokument_id)
        zusammenfassung["entfernt"] += 1

    # Pass 3: Nachmaskierung. Lernt die NER einen Namen erst in diesem Lauf,
    # kann er noch im Klartext in früher indexierten (unveränderten)
    # Dokumenten stehen — die werden hier erneut maskiert und neu indexiert.
    neu_ids = {doku["id"] for _, doku, _ in zu_indexieren}
    for dokument_id in sorted((set(vorhandene) & gesehen) - neu_ids):
        titel, dateiname, jahr, groesse, volltext = con.execute(
            "SELECT titel, dateiname, jahr, groesse, volltext FROM dokumente "
            "WHERE id = ?", (dokument_id,)).fetchone()
        maskiert, mapping = masker.maskiere(volltext, dokument_id=dokument_id)
        if maskiert == volltext:
            continue
        mapping_gesamt.update(mapping)
        chunks = index.chunke(maskiert)
        vektoren = embeddings.embed_passagen(chunks)
        index.speichere_dokument(con, {
            "id": dokument_id, "titel": titel, "dateiname": dateiname,
            "jahr": jahr, "groesse": groesse, "volltext": maskiert,
        }, chunks, vektoren)
        zusammenfassung["nachmaskiert"] += 1

    # Vermerk bei JEDEM abgeschlossenen Lauf, auch ohne Änderung: die
    # Statuszeile soll "zuletzt geprüft" zeigen, nicht "zuletzt geschrieben".
    index.setze_meta(con, "letzter_ingest", _jetzt())
    con.close()

    if mapping_gesamt:
        zeilen = [f"- {pseudo} = {name}" for pseudo, name in sorted(mapping_gesamt.items())]
        zusammenfassung["mapping_datei"] = privacy.schreibe_namensliste(
            "pseudonym_mapping.md", "Pseudonym-Mapping (nur lokal!)", zeilen)

    logger.info("Ingest: %(neu)d neu, %(unveraendert)d unverändert, "
                "%(entfernt)d entfernt, %(nachmaskiert)d nachmaskiert, "
                "%(anzahl_ueb)d übersprungen, %(anzahl_fehler)d Fehler",
                {**zusammenfassung,
                 "anzahl_ueb": len(zusammenfassung["uebersprungen"]),
                 "anzahl_fehler": len(zusammenfassung["fehler"])})
    return zusammenfassung
