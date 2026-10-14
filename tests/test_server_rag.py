"""Tests für die RAG-Tools inkl. PII-Sweep über die komplette Maskierungs-Pipeline."""

import json

from webling_mcp import server
from webling_mcp.rag.maskierung import Maskierer

# Direkter Modul-Import: tests/ hat kein __init__.py, pytest legt das
# Verzeichnis selbst auf den sys.path
from test_server_antworten import VERBOTENE_WERTE, VERBOTENE_SCHLUESSEL, _alle_schluessel


class FakeNlp:
    def __init__(self, namen):
        self._namen = namen

    def __call__(self, text):
        class Ent:
            def __init__(self, t):
                self.text = t
                self.label_ = "PER"

        class Doc:
            pass

        doc = Doc()
        doc.ents = [Ent(n) for n in self._namen if n in text]
        return doc


def test_pii_sweep_ueber_rag_pipeline_und_tools(mitglieder):
    """DER kritische Phase-B-Test: Maskierung + Tool-Antworten sind PII-frei."""
    protokoll = ("Erika Musterfrau eröffnet. Mustermann, Max fehlt entschuldigt. "
                 "Gast Hans Besucher (hans@example.com, Tel. 0123 123456) berichtet. "
                 "Otto Ohnedaten, geboren 15.03.1961, IBAN DE89 3704 0044 0532 0130 00.")
    masker = Maskierer(mitglieder, nlp=FakeNlp(["Hans Besucher"]))

    maskiert, _ = masker.maskiere(protokoll, dokument_id=55)

    treffer = [{"text": maskiert, "dokument": "Protokoll", "jahr": "2026",
                "dokument_id": 55, "score": 0.03}]
    antworten = [
        server.baue_suche_dokumente(treffer),
        server.baue_lies_dokument({"dokument": "Protokoll", "jahr": "2026",
                                   "text": maskiert}, 55),
        server.baue_lies_dokument(None, 999),
    ]
    for antwort in antworten:
        text = json.dumps(antwort, ensure_ascii=False)
        for wert in VERBOTENE_WERTE + ["Besucher", "hans@example.com", "123456",
                                       "0532", "15.03.1961"]:
            assert wert not in text, f"PII-Leak: '{wert}'"
        assert not _alle_schluessel(antwort) & VERBOTENE_SCHLUESSEL


def test_baue_suche_dokumente_struktur():
    treffer = [{"text": "M-101 eröffnet.", "dokument": "Protokoll", "jahr": "2026",
                "dokument_id": 55, "score": 0.03}]

    antwort = server.baue_suche_dokumente(treffer)

    assert antwort["anzahl"] == 1
    assert antwort["treffer"] == treffer
    assert "pseudonym_mapping.md" in antwort["hinweis"]


def test_baue_lies_dokument_unbekannte_id():
    antwort = server.baue_lies_dokument(None, 999)

    assert "999" in antwort["fehler"]
