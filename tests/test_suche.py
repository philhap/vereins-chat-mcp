"""Tests für die Hybridsuche. Deterministische Fake-Embeddings statt echtem Modell."""

import hashlib

import pytest

from webling_mcp.rag import embeddings, index, suche


def fake_vektor(text: str) -> list[float]:
    """Deterministischer Pseudo-Vektor: identischer Text -> identischer Vektor."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    werte = [b / 255 for b in h] * (embeddings.DIMENSION // len(h) + 1)
    return werte[: embeddings.DIMENSION]


@pytest.fixture
def befuellter_index(tmp_index, monkeypatch):
    monkeypatch.setattr(embeddings, "embed_frage", lambda frage: fake_vektor(frage))
    con = index.oeffne_db()
    dokumente = [
        ({"id": 1, "titel": "Protokoll März", "dateiname": "p1.pdf", "jahr": "2025",
          "groesse": 1, "volltext": "Beschluss zur Beitragserhöhung auf 150 Euro."},
         ["Beschluss zur Beitragserhöhung auf 150 Euro."]),
        ({"id": 2, "titel": "Satzung", "dateiname": "satzung.pdf", "jahr": "2020",
          "groesse": 1, "volltext": "Die Kündigung ist schriftlich zu erklären."},
         ["Die Kündigung ist schriftlich zu erklären."]),
    ]
    for meta, chunks in dokumente:
        index.speichere_dokument(con, meta, chunks, [fake_vektor(c) for c in chunks])
    con.close()
    return tmp_index


def test_keyword_treffer(befuellter_index):
    treffer = suche.suche("Beitragserhöhung")

    assert treffer[0]["dokument"] == "Protokoll März"
    assert treffer[0]["jahr"] == "2025"
    assert "150 Euro" in treffer[0]["text"]
    assert treffer[0]["score"] > 0


def test_vektor_treffer_bei_identischem_text(befuellter_index):
    # Fake-Vektor der Frage == Fake-Vektor des Chunks -> Vektor-Ast MUSS ihn finden
    treffer = suche.suche("Die Kündigung ist schriftlich zu erklären.")

    assert treffer[0]["dokument"] == "Satzung"


def test_jahr_filter(befuellter_index):
    treffer = suche.suche("Beitragserhöhung", jahr="2020")

    assert all(t["jahr"] == "2020" for t in treffer)


def test_max_treffer(befuellter_index):
    assert len(suche.suche("schriftlich Beitragserhöhung", max_treffer=1)) <= 1


def test_leere_frage_liefert_leere_liste(befuellter_index):
    assert suche.suche("   ") == []


def test_lies_volltext(befuellter_index):
    dok = suche.lies_volltext(2)

    assert dok["dokument"] == "Satzung"
    assert "schriftlich" in dok["text"]
    assert suche.lies_volltext(999) is None


@pytest.fixture
def komposita_index(tmp_index, monkeypatch):
    """Eigenes Fixture für die Komposita-Tests (getrennt vom Plan-Fixture)."""
    monkeypatch.setattr(embeddings, "embed_frage", lambda frage: fake_vektor(frage))
    con = index.oeffne_db()
    dokumente = [
        ({"id": 10, "titel": "Protokoll JHV 2024", "dateiname": "p10.docx", "jahr": "2024",
          "groesse": 1, "volltext": "Die Beiträge werden zum Saisonstart erhöht."},
         ["Die Beiträge werden zum Saisonstart erhöht."]),
        ({"id": 11, "titel": "Protokoll März", "dateiname": "p11.pdf", "jahr": "2025",
          "groesse": 1, "volltext": "Beschluss zur Beitragserhöhung auf 150 Euro."},
         ["Beschluss zur Beitragserhöhung auf 150 Euro."]),
    ]
    for meta, chunks in dokumente:
        index.speichere_dokument(con, meta, chunks, [fake_vektor(c) for c in chunks])
    con.close()
    return tmp_index


def test_kompositum_findet_teilwoerter(komposita_index):
    """Deutsche Komposita: 'Beitragserhöhung' muss ein Dokument finden, das nur
    'Beiträge ... erhöht' enthält (Präfix-Expansion im FTS-Ast)."""
    treffer = suche.suche("Beitragserhöhung")

    assert any(t["dokument"] == "Protokoll JHV 2024" for t in treffer)


def test_teilwort_findet_kompositum(komposita_index):
    """Umgekehrt: 'Beiträge' findet auch das Dokument mit 'Beitragserhöhung'."""
    treffer = suche.suche("Beiträge")

    assert any(t["dokument"] == "Protokoll März" for t in treffer)
