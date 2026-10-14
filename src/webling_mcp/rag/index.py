"""
Lokaler Suchindex: eine SQLite-Datei mit FTS5 (BM25) + sqlite-vec (Vektoren).

Enthält AUSSCHLIESSLICH maskierten Text (Maskierung passiert davor im
Ingest) — kann konstruktionsbedingt keine Klarnamen leaken.
"""

import logging
import os
import sqlite3
from pathlib import Path

import sqlite_vec

from webling_mcp.rag.embeddings import DIMENSION

logger = logging.getLogger(__name__)

# Env-Override analog zu privacy.OUTPUT_DIR
INDEX_DIR = Path(
    os.environ.get("WEBLING_MCP_INDEX_DIR")
    or Path(__file__).resolve().parents[3] / "index"
)


def db_datei() -> Path:
    return INDEX_DIR / "webling.db"


def oeffne_db() -> sqlite3.Connection:
    """Öffnet die Index-DB, lädt sqlite-vec und legt das Schema an (idempotent)."""
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_datei())
    con.enable_load_extension(True)
    sqlite_vec.load(con)
    con.enable_load_extension(False)
    con.executescript(f"""
        CREATE TABLE IF NOT EXISTS dokumente(
            id INTEGER PRIMARY KEY, titel TEXT, dateiname TEXT,
            jahr TEXT, groesse INTEGER, volltext TEXT);
        CREATE TABLE IF NOT EXISTS chunks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dokument_id INTEGER NOT NULL, position INTEGER NOT NULL, text TEXT NOT NULL);
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text);
        CREATE VIRTUAL TABLE IF NOT EXISTS vektoren USING vec0(embedding float[{DIMENSION}]);
        CREATE TABLE IF NOT EXISTS meta(schluessel TEXT PRIMARY KEY, wert TEXT);
    """)
    return con


def setze_meta(con: sqlite3.Connection, schluessel: str, wert: str) -> None:
    """Betriebsdaten zum Index (z.B. Zeitpunkt des letzten Ingest-Laufs).
    Keine Dokumentinhalte — die Tabelle ist für Zustand, nicht für Text."""
    con.execute("INSERT INTO meta(schluessel, wert) VALUES(?, ?) "
                "ON CONFLICT(schluessel) DO UPDATE SET wert = excluded.wert",
                (schluessel, wert))
    con.commit()


def hole_meta(con: sqlite3.Connection, schluessel: str) -> str | None:
    zeile = con.execute("SELECT wert FROM meta WHERE schluessel = ?",
                        (schluessel,)).fetchone()
    return zeile[0] if zeile else None


def chunke(text: str, max_woerter: int = 300, ueberlappung: int = 40) -> list[str]:
    """Zerteilt Text in überlappende Wort-Chunks (~400 Tokens ≈ 300 Wörter)."""
    woerter = text.split()
    if not woerter:
        return []
    chunks, start = [], 0
    while start < len(woerter):
        chunks.append(" ".join(woerter[start:start + max_woerter]))
        if start + max_woerter >= len(woerter):
            break
        start += max_woerter - ueberlappung
    return chunks


def _loesche_chunks(con: sqlite3.Connection, dokument_id: int) -> None:
    chunk_ids = [r[0] for r in con.execute(
        "SELECT id FROM chunks WHERE dokument_id = ?", (dokument_id,)
    )]
    for cid in chunk_ids:
        con.execute("DELETE FROM chunks_fts WHERE rowid = ?", (cid,))
        con.execute("DELETE FROM vektoren WHERE rowid = ?", (cid,))
    con.execute("DELETE FROM chunks WHERE dokument_id = ?", (dokument_id,))


def speichere_dokument(con: sqlite3.Connection, meta: dict,
                       chunks: list[str], vektoren: list[list[float]]) -> None:
    """Schreibt ein (bereits maskiertes) Dokument in den Index; ersetzt Altbestand."""
    _loesche_chunks(con, meta["id"])
    con.execute("DELETE FROM dokumente WHERE id = ?", (meta["id"],))
    con.execute(
        "INSERT INTO dokumente(id, titel, dateiname, jahr, groesse, volltext) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (meta["id"], meta["titel"], meta["dateiname"], meta["jahr"],
         meta["groesse"], meta["volltext"]),
    )
    for position, (chunk, vektor) in enumerate(zip(chunks, vektoren)):
        cursor = con.execute(
            "INSERT INTO chunks(dokument_id, position, text) VALUES (?, ?, ?)",
            (meta["id"], position, chunk),
        )
        cid = cursor.lastrowid
        con.execute("INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)", (cid, chunk))
        con.execute("INSERT INTO vektoren(rowid, embedding) VALUES (?, ?)",
                    (cid, sqlite_vec.serialize_float32(vektor)))
    con.commit()
    logger.info("Dokument %s indexiert: %d Chunks", meta["id"], len(chunks))


def loesche_dokument(con: sqlite3.Connection, dokument_id: int) -> None:
    """Entfernt ein Dokument samt Chunks/Vektoren (z.B. in Webling gelöscht)."""
    _loesche_chunks(con, dokument_id)
    con.execute("DELETE FROM dokumente WHERE id = ?", (dokument_id,))
    con.commit()


def indexierte_dokumente(con: sqlite3.Connection) -> dict[int, int]:
    """{dokument_id: groesse} — Grundlage für den inkrementellen Sync."""
    return dict(con.execute("SELECT id, groesse FROM dokumente"))
