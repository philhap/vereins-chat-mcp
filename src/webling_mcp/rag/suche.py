"""
Hybridsuche über den maskierten Index: BM25 (FTS5) + Vektoren (sqlite-vec),
kombiniert per Reciprocal Rank Fusion (RRF, k=60, keine Tuning-Parameter).
"""

import logging
import re

import sqlite_vec

from webling_mcp.rag import embeddings, index

logger = logging.getLogger(__name__)

RRF_K = 60
# Kandidatenfenster pro Suchast — großzügig, weil der Jahr-Filter erst NACH
# der Kandidatensuche greift und der Index klein ist (SQLite, lokal).
KANDIDATEN = 200


def _fts_kandidaten(con, frage: str) -> list[int]:
    """BM25-Kandidaten: Chunk-IDs nach FTS5-Rang (Frage OR-verknüpft, Syntax-sicher)."""
    begriffe = re.findall(r"\w+", frage)
    if not begriffe:
        return []
    terme = [f'"{b}"' for b in begriffe]
    # Deutsche Komposita: lange Wörter zusätzlich als Präfix suchen, damit
    # "Beitragserhöhung" auch "Beiträge" findet (und umgekehrt).
    terme += [f'"{b[:5]}"*' for b in begriffe if len(b) >= 8]
    query = " OR ".join(dict.fromkeys(terme))
    zeilen = con.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
        (query, KANDIDATEN),
    ).fetchall()
    return [z[0] for z in zeilen]


def _vektor_kandidaten(con, frage: str) -> list[int]:
    """Vektor-Kandidaten: Chunk-IDs nach Embedding-Distanz."""
    vektor = embeddings.embed_frage(frage)
    zeilen = con.execute(
        "SELECT rowid FROM vektoren WHERE embedding MATCH ? AND k = ? ORDER BY distance",
        (sqlite_vec.serialize_float32(vektor), KANDIDATEN),
    ).fetchall()
    return [z[0] for z in zeilen]


def suche(frage: str, jahr: str | None = None, max_treffer: int = 5) -> list[dict]:
    """Hybridsuche; Treffer absteigend nach RRF-Score, optional auf ein Jahr gefiltert."""
    if not frage.strip():
        return []
    con = index.oeffne_db()
    try:
        punkte: dict[int, float] = {}
        for kandidaten in (_fts_kandidaten(con, frage), _vektor_kandidaten(con, frage)):
            for rang, cid in enumerate(kandidaten):
                punkte[cid] = punkte.get(cid, 0.0) + 1.0 / (RRF_K + rang + 1)

        treffer = []
        for cid in sorted(punkte, key=punkte.get, reverse=True):
            zeile = con.execute(
                "SELECT c.text, d.titel, d.jahr, d.id FROM chunks c "
                "JOIN dokumente d ON d.id = c.dokument_id WHERE c.id = ?",
                (cid,),
            ).fetchone()
            if zeile is None:
                continue
            text, titel, dok_jahr, dok_id = zeile
            if jahr is not None and dok_jahr != jahr:
                continue
            treffer.append({"text": text, "dokument": titel, "jahr": dok_jahr,
                            "dokument_id": dok_id, "score": round(punkte[cid], 4)})
            if len(treffer) >= max_treffer:
                break
        logger.info("Suche: %d Kandidaten, %d Treffer", len(punkte), len(treffer))
        return treffer
    finally:
        con.close()


def lies_volltext(dokument_id: int) -> dict | None:
    """Maskierter Volltext eines Dokuments (für Nachfassen nach einem Suchtreffer)."""
    con = index.oeffne_db()
    try:
        zeile = con.execute(
            "SELECT titel, jahr, volltext FROM dokumente WHERE id = ?", (dokument_id,)
        ).fetchone()
    finally:
        con.close()
    if zeile is None:
        return None
    return {"dokument": zeile[0], "jahr": zeile[1], "text": zeile[2]}
