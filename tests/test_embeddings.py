"""Tests für das Embeddings-Modul — das echte Modell wird NIE geladen (Fake via monkeypatch)."""

from webling_mcp.rag import embeddings


class FakeModell:
    def __init__(self):
        self.aufrufe = []

    def encode(self, texte, normalize_embeddings=True):
        self.aufrufe.append(list(texte))
        return [[0.1] * embeddings.DIMENSION for _ in texte]


def test_embed_passagen_nutzt_e5_prefix(monkeypatch):
    fake = FakeModell()
    monkeypatch.setattr(embeddings, "_lade_modell", lambda: fake)

    vektoren = embeddings.embed_passagen(["Hallo Welt", "Zweiter Chunk"])

    assert fake.aufrufe[0] == ["passage: Hallo Welt", "passage: Zweiter Chunk"]
    assert len(vektoren) == 2 and len(vektoren[0]) == embeddings.DIMENSION


def test_embed_frage_nutzt_query_prefix(monkeypatch):
    fake = FakeModell()
    monkeypatch.setattr(embeddings, "_lade_modell", lambda: fake)

    vektor = embeddings.embed_frage("Was steht in der Satzung?")

    assert fake.aufrufe[0] == ["query: Was steht in der Satzung?"]
    assert len(vektor) == embeddings.DIMENSION


def test_embed_passagen_leere_liste():
    assert embeddings.embed_passagen([]) == []
