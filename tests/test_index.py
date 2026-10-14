"""Tests für Chunking und SQLite-Index (FTS5 + sqlite-vec). Fake-Vektoren, kein Modell."""

from webling_mcp.rag import embeddings, index


def fake_vektor(wert: float = 0.5) -> list[float]:
    return [wert] * embeddings.DIMENSION


def meta(dok_id: int, jahr: str = "2026", groesse: int = 100) -> dict:
    return {"id": dok_id, "titel": f"Dok {dok_id}", "dateiname": f"dok{dok_id}.pdf",
            "jahr": jahr, "groesse": groesse, "volltext": f"Volltext {dok_id}"}


def test_chunke_kurzer_text_ein_chunk():
    assert index.chunke("eins zwei drei") == ["eins zwei drei"]


def test_chunke_leerer_text():
    assert index.chunke("   ") == []


def test_chunke_lange_texte_mit_ueberlappung():
    woerter = [f"w{i}" for i in range(700)]
    chunks = index.chunke(" ".join(woerter), max_woerter=300, ueberlappung=40)

    assert len(chunks) == 3
    # Überlappung: die letzten 40 Wörter von Chunk 1 sind die ersten 40 von Chunk 2
    assert chunks[0].split()[-40:] == chunks[1].split()[:40]


def test_meta_speichern_lesen_und_ueberschreiben(tmp_index):
    con = index.oeffne_db()

    assert index.hole_meta(con, "letzter_ingest") is None
    index.setze_meta(con, "letzter_ingest", "2026-07-21T12:04:00")
    assert index.hole_meta(con, "letzter_ingest") == "2026-07-21T12:04:00"
    index.setze_meta(con, "letzter_ingest", "2026-07-22T09:00:00")
    assert index.hole_meta(con, "letzter_ingest") == "2026-07-22T09:00:00"


def test_speichern_und_wiederfinden(tmp_index):
    con = index.oeffne_db()
    index.speichere_dokument(con, meta(1), ["chunk eins", "chunk zwei"],
                             [fake_vektor(0.1), fake_vektor(0.2)])

    assert index.indexierte_dokumente(con) == {1: 100}
    treffer = con.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?", ('"zwei"',)
    ).fetchall()
    assert len(treffer) == 1
    assert con.execute("SELECT COUNT(*) FROM vektoren").fetchone()[0] == 2


def test_erneutes_speichern_ersetzt_altbestand(tmp_index):
    con = index.oeffne_db()
    index.speichere_dokument(con, meta(1), ["alt"], [fake_vektor()])
    index.speichere_dokument(con, meta(1, groesse=200), ["neu"], [fake_vektor()])

    assert index.indexierte_dokumente(con) == {1: 200}
    assert con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 1
    assert con.execute(
        "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?", ('"alt"',)
    ).fetchone()[0] == 0


def test_loesche_dokument(tmp_index):
    con = index.oeffne_db()
    index.speichere_dokument(con, meta(1), ["bleibt"], [fake_vektor()])
    index.speichere_dokument(con, meta(2), ["weg"], [fake_vektor()])

    index.loesche_dokument(con, 2)

    assert index.indexierte_dokumente(con) == {1: 100}
    assert con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM vektoren").fetchone()[0] == 1
