"""Tests für den inkrementellen Ingest. Client, NER und Embeddings sind gefälscht."""

from io import BytesIO

from webling_mcp.rag import embeddings, index, ingest


def docx_bytes(text: str) -> bytes:
    from docx import Document

    d = Document()
    d.add_paragraph(text)
    puffer = BytesIO()
    d.save(puffer)
    return puffer.getvalue()


class FakeNlpLeer:
    def __call__(self, text):
        class Doc:
            ents = []

        return Doc()


def richte_fakes_ein(monkeypatch, mitglieder, dokumente_pro_jahr, inhalte):
    """dokumente_pro_jahr: {jahr: [{'id','title','name','size'}]}; inhalte: {id: bytes}."""
    from webling_mcp.client import documents, members

    monkeypatch.setattr(documents, "alle_dokumentordner",
                        lambda: [(jahr, i) for i, jahr in enumerate(sorted(dokumente_pro_jahr))])
    monkeypatch.setattr(documents, "liste_dokumente",
                        lambda ordner_id: dokumente_pro_jahr[sorted(dokumente_pro_jahr)[ordner_id]])
    monkeypatch.setattr(documents, "lade_dokument", lambda did: inhalte[did])
    monkeypatch.setattr(members, "hole_alle_mitglieder", lambda: mitglieder)
    monkeypatch.setattr(embeddings, "embed_passagen",
                        lambda texte: [[0.1] * embeddings.DIMENSION for _ in texte])
    monkeypatch.setattr(ingest, "_nlp_fuer_ingest", lambda: FakeNlpLeer())


def test_ingest_indexiert_maskiert_und_schreibt_mapping(
        mitglieder, tmp_index, tmp_output, monkeypatch):
    richte_fakes_ein(
        monkeypatch, mitglieder,
        {"2026": [{"id": 55, "title": "Protokoll", "name": "protokoll.docx", "size": 10}]},
        {55: docx_bytes("Erika Musterfrau eröffnet die Sitzung.")},
    )

    ergebnis = ingest.synchronisiere()

    assert ergebnis["neu"] == 1 and ergebnis["unveraendert"] == 0
    con = index.oeffne_db()
    volltext = con.execute("SELECT volltext FROM dokumente WHERE id = 55").fetchone()[0]
    assert "Erika" not in volltext and "M-101" in volltext
    mapping = (tmp_output / "pseudonym_mapping.md").read_text(encoding="utf-8")
    assert "- M-101 = Erika Musterfrau" in mapping


def test_ingest_vermerkt_zeitpunkt_auch_ohne_aenderung(
        mitglieder, tmp_index, tmp_output, monkeypatch):
    """Der Vermerk muss bei JEDEM abgeschlossenen Lauf fortschreiben, auch wenn
    kein Dokument neu ist. Sonst zeigt die Statuszeile einen tagealten Stand an
    und ein aktueller Index sieht aus wie eine kaputte Automatik."""
    dok = {"id": 55, "title": "Protokoll", "name": "protokoll.docx", "size": 10}
    richte_fakes_ein(monkeypatch, mitglieder, {"2026": [dok]},
                     {55: docx_bytes("Text ohne Namen.")})
    zeiten = iter(["2026-07-21T09:00:00", "2026-07-22T09:00:00"])
    monkeypatch.setattr(ingest, "_jetzt", lambda: next(zeiten))

    ingest.synchronisiere()
    con = index.oeffne_db()
    erster = index.hole_meta(con, "letzter_ingest")
    con.close()

    zweiter_lauf = ingest.synchronisiere()
    con = index.oeffne_db()
    zweiter = index.hole_meta(con, "letzter_ingest")
    con.close()

    assert zweiter_lauf["neu"] == 0 and zweiter_lauf["unveraendert"] == 1
    assert erster == "2026-07-21T09:00:00"
    assert zweiter == "2026-07-22T09:00:00"


def test_ingest_ist_inkrementell(mitglieder, tmp_index, tmp_output, monkeypatch):
    dok = {"id": 55, "title": "Protokoll", "name": "protokoll.docx", "size": 10}
    richte_fakes_ein(monkeypatch, mitglieder, {"2026": [dok]},
                     {55: docx_bytes("Text ohne Namen.")})

    ingest.synchronisiere()
    zweiter = ingest.synchronisiere()

    assert zweiter["neu"] == 0 and zweiter["unveraendert"] == 1


def test_ingest_entfernt_geloeschte_dokumente(mitglieder, tmp_index, tmp_output, monkeypatch):
    richte_fakes_ein(monkeypatch, mitglieder,
                     {"2026": [{"id": 55, "title": "Alt", "name": "alt.docx", "size": 10}]},
                     {55: docx_bytes("Alter Inhalt.")})
    ingest.synchronisiere()

    richte_fakes_ein(monkeypatch, mitglieder, {"2026": []}, {})
    ergebnis = ingest.synchronisiere()

    assert ergebnis["entfernt"] == 1
    con = index.oeffne_db()
    assert index.indexierte_dokumente(con) == {}


def test_ingest_meldet_nicht_extrahierbare(mitglieder, tmp_index, tmp_output, monkeypatch):
    richte_fakes_ein(monkeypatch, mitglieder,
                     {"2026": [{"id": 56, "title": "Foto", "name": "foto.jpg", "size": 5}]},
                     {56: b"\xff\xd8\xff"})

    ergebnis = ingest.synchronisiere()

    assert ergebnis["uebersprungen"] == ["foto.jpg"]
    assert ergebnis["neu"] == 0


def test_download_fehler_bricht_lauf_nicht_ab(mitglieder, tmp_index, tmp_output, monkeypatch):
    """Ein Verbindungsfehler bei einem Dokument (z.B. Rate-Limit) darf weder die
    übrigen Dokumente noch das Schreiben des Pseudonym-Mappings verhindern."""
    from webling_mcp.client import documents

    richte_fakes_ein(monkeypatch, mitglieder,
                     {"2026": [{"id": 55, "title": "OK", "name": "ok.docx", "size": 10},
                               {"id": 56, "title": "Kaputt", "name": "kaputt.docx", "size": 10}]},
                     {55: docx_bytes("Erika Musterfrau war da.")})

    def lade_mit_fehler(did):
        if did == 56:
            raise ConnectionError("Verbindung zurückgesetzt")
        return docx_bytes("Erika Musterfrau war da.")

    monkeypatch.setattr(documents, "lade_dokument", lade_mit_fehler)

    ergebnis = ingest.synchronisiere()

    assert ergebnis["neu"] == 1
    assert ergebnis["fehler"] == ["kaputt.docx"]
    mapping = (tmp_output / "pseudonym_mapping.md").read_text(encoding="utf-8")
    assert "- M-101 = Erika Musterfrau" in mapping


class FakeNlpEinmalig:
    """Meldet den Namen nur beim ersten Aufruf — simuliert NER-Inkonsistenz."""

    def __init__(self, name):
        self._name = name

    def __call__(self, text):
        class Ent:
            pass

        class Doc:
            ents = []

        doc = Doc()
        if self._name and self._name in text:
            ent = Ent()
            ent.text, ent.label_ = self._name, "PER"
            doc.ents = [ent]
            self._name = None
        return doc


def test_ner_fund_gilt_fuer_alle_dokumente_des_laufs(
        mitglieder, tmp_index, tmp_output, monkeypatch):
    """Erkennt die NER einen Namen nur in einem Dokument, muss er trotzdem
    in ALLEN Dokumenten des Laufs maskiert werden (Vorab-Pass)."""
    richte_fakes_ein(monkeypatch, mitglieder,
                     {"2026": [{"id": 55, "title": "A", "name": "a.docx", "size": 10},
                               {"id": 56, "title": "B", "name": "b.docx", "size": 10}]},
                     {55: docx_bytes("Gast: Hans Besucher vom Verband."),
                      56: docx_bytes("Hans Besucher war erneut anwesend.")})
    monkeypatch.setattr(ingest, "_nlp_fuer_ingest",
                        lambda: FakeNlpEinmalig("Hans Besucher"))

    ingest.synchronisiere()

    con = index.oeffne_db()
    for dok_id in (55, 56):
        volltext = con.execute(
            "SELECT volltext FROM dokumente WHERE id = ?", (dok_id,)).fetchone()[0]
        assert "Hans Besucher" not in volltext, f"Leak in Dokument {dok_id}"


def test_ingest_nutzt_bestehendes_mapping_als_fremdliste(
        mitglieder, tmp_index, tmp_output, monkeypatch):
    """Fremd-Namen aus einem früheren Lauf (Mapping-Datei) werden auch ohne
    erneuten NER-Fund maskiert."""
    tmp_output.mkdir(parents=True, exist_ok=True)
    (tmp_output / "pseudonym_mapping.md").write_text(
        "# Pseudonym-Mapping (nur lokal!)\n\n- P-1-1 = Hans Besucher\n",
        encoding="utf-8")
    richte_fakes_ein(monkeypatch, mitglieder,
                     {"2026": [{"id": 55, "title": "A", "name": "a.docx", "size": 10}]},
                     {55: docx_bytes("Hans Besucher stellt den Antrag.")})

    ingest.synchronisiere()

    con = index.oeffne_db()
    volltext = con.execute("SELECT volltext FROM dokumente WHERE id = 55").fetchone()[0]
    assert "Hans Besucher" not in volltext


def test_ingest_erfasst_auch_nicht_jahres_ordner(mitglieder, tmp_index, tmp_output, monkeypatch):
    """Dokumente in Ordnern wie 'Satzungen' oder 'Öffentliche Daten' gehören
    auch in den Index; der Ordnertitel landet im jahr-Feld."""
    richte_fakes_ein(monkeypatch, mitglieder,
                     {"Satzungen": [{"id": 60, "title": "Satzung",
                                     "name": "satzung.docx", "size": 10}]},
                     {60: docx_bytes("Die Kündigung ist schriftlich zu erklären.")})

    ergebnis = ingest.synchronisiere()

    assert ergebnis["neu"] == 1
    con = index.oeffne_db()
    assert con.execute("SELECT jahr FROM dokumente WHERE id = 60").fetchone()[0] == "Satzungen"


def test_mapping_wird_uebergreifend_gemerged(mitglieder, tmp_index, tmp_output, monkeypatch):
    # Lauf 1: Dokument 55 erzeugt Mapping-Eintrag
    richte_fakes_ein(monkeypatch, mitglieder,
                     {"2026": [{"id": 55, "title": "P1", "name": "p1.docx", "size": 10}]},
                     {55: docx_bytes("Erika Musterfrau war da.")})
    ingest.synchronisiere()

    # Lauf 2: Dokument 55 unverändert, neues Dokument 57 — alter Eintrag bleibt
    richte_fakes_ein(monkeypatch, mitglieder,
                     {"2026": [{"id": 55, "title": "P1", "name": "p1.docx", "size": 10},
                               {"id": 57, "title": "P2", "name": "p2.docx", "size": 10}]},
                     {57: docx_bytes("Max Mustermann war auch da.")})
    ingest.synchronisiere()

    mapping = (tmp_output / "pseudonym_mapping.md").read_text(encoding="utf-8")
    assert "- M-101 = Erika Musterfrau" in mapping
    assert "- M-102 = Max Mustermann" in mapping


def test_neu_gelernte_namen_werden_rueckwirkend_maskiert(
        mitglieder, tmp_index, tmp_output, monkeypatch):
    """Findet die NER einen Namen erst in einem SPÄTEREN Lauf, muss ein früher
    indexiertes Dokument mit diesem Namen nachmaskiert werden."""
    # Lauf 1: Dokument 55 enthält den Namen, aber die NER übersieht ihn
    richte_fakes_ein(monkeypatch, mitglieder,
                     {"2026": [{"id": 55, "title": "Alt", "name": "alt.docx", "size": 10}]},
                     {55: docx_bytes("Hans Besucher stellt den Antrag.")})
    ingest.synchronisiere()
    con = index.oeffne_db()
    assert "Hans Besucher" in con.execute(
        "SELECT volltext FROM dokumente WHERE id = 55").fetchone()[0]
    con.close()

    # Lauf 2: neues Dokument 56, in dem die NER den Namen erkennt
    richte_fakes_ein(monkeypatch, mitglieder,
                     {"2026": [{"id": 55, "title": "Alt", "name": "alt.docx", "size": 10},
                               {"id": 56, "title": "Neu", "name": "neu.docx", "size": 10}]},
                     {55: docx_bytes("Hans Besucher stellt den Antrag."),
                      56: docx_bytes("Gast: Hans Besucher vom Verband.")})
    monkeypatch.setattr(ingest, "_nlp_fuer_ingest",
                        lambda: FakeNlpEinmalig("Hans Besucher"))

    ergebnis = ingest.synchronisiere()

    assert ergebnis["nachmaskiert"] == 1
    con = index.oeffne_db()
    for dok_id in (55, 56):
        volltext = con.execute(
            "SELECT volltext FROM dokumente WHERE id = ?", (dok_id,)).fetchone()[0]
        assert "Hans Besucher" not in volltext, f"Leak in Dokument {dok_id}"


def test_nachmaskierung_vergibt_keine_doppelten_pseudonyme(
        mitglieder, tmp_index, tmp_output, monkeypatch):
    """Enthält ein Dokument bereits P-<id>-1 aus einem früheren Lauf, darf ein
    nachmaskierter neuer Name nicht wieder P-<id>-1 bekommen — sonst teilen
    sich zwei Personen ein Pseudonym und der alte Mapping-Eintrag geht verloren."""
    # Lauf 1: NER erkennt nur "Anna Alt" -> P-55-1; "Hans Besucher" bleibt stehen
    richte_fakes_ein(monkeypatch, mitglieder,
                     {"2026": [{"id": 55, "title": "Alt", "name": "alt.docx", "size": 10}]},
                     {55: docx_bytes("Anna Alt und Hans Besucher stellen den Antrag.")})
    monkeypatch.setattr(ingest, "_nlp_fuer_ingest",
                        lambda: FakeNlpEinmalig("Anna Alt"))
    ingest.synchronisiere()

    # Lauf 2: neues Dokument 56, in dem die NER "Hans Besucher" erkennt
    richte_fakes_ein(monkeypatch, mitglieder,
                     {"2026": [{"id": 55, "title": "Alt", "name": "alt.docx", "size": 10},
                               {"id": 56, "title": "Neu", "name": "neu.docx", "size": 10}]},
                     {55: docx_bytes("Anna Alt und Hans Besucher stellen den Antrag."),
                      56: docx_bytes("Gast: Hans Besucher vom Verband.")})
    monkeypatch.setattr(ingest, "_nlp_fuer_ingest",
                        lambda: FakeNlpEinmalig("Hans Besucher"))

    ingest.synchronisiere()

    con = index.oeffne_db()
    volltext = con.execute(
        "SELECT volltext FROM dokumente WHERE id = 55").fetchone()[0]
    assert "Hans Besucher" not in volltext
    assert "P-55-1" in volltext and "P-55-2" in volltext
    mapping = (tmp_output / "pseudonym_mapping.md").read_text(encoding="utf-8")
    assert "- P-55-1 = Anna Alt" in mapping
    assert "- P-55-2 = Hans Besucher" in mapping
