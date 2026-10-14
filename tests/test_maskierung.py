"""Tests für die zweistufige PII-Maskierung. Nur fiktive Personen, kein echtes spaCy."""

from webling_mcp.rag.maskierung import Maskierer, namensvarianten


class FakeEnt:
    def __init__(self, text, label):
        self.text = text
        self.label_ = label


class FakeNlp:
    """Ersetzt spaCy in Tests: meldet vorgegebene Namen als PER-Entitäten."""

    def __init__(self, namen):
        self._namen = namen

    def __call__(self, text):
        class Doc:
            pass

        doc = Doc()
        doc.ents = [FakeEnt(n, "PER") for n in self._namen if n in text]
        return doc


class FakeNlpEinmalig(FakeNlp):
    """Meldet Entitäten nur beim ERSTEN Aufruf — simuliert die reale
    NER-Inkonsistenz (Name in Dokument A erkannt, in Dokument B übersehen)."""

    def __call__(self, text):
        doc = super().__call__(text)
        self._namen = []
        return doc


def test_namensvarianten():
    assert namensvarianten("Max", "Mustermann") == [
        "Max Mustermann", "Mustermann, Max", "M. Mustermann",
    ]
    assert namensvarianten("", "Mustermann") == ["Mustermann"]
    assert namensvarianten("Max", "") == []


def test_mitglieder_werden_in_allen_varianten_maskiert(mitglieder):
    m = Maskierer(mitglieder, nlp=FakeNlp([]))
    text = ("Erika Musterfrau eröffnet. Mustermann, Max fehlt. "
            "M. Mustermann hat sich entschuldigt. Frau Musterfrau schließt.")

    maskiert, mapping = m.maskiere(text, dokument_id=55)

    assert "Erika" not in maskiert and "Musterfrau" not in maskiert
    assert "Max" not in maskiert and "Mustermann" not in maskiert
    assert maskiert.count("M-101") == 2
    assert maskiert.count("M-102") == 2
    assert mapping["M-101"] == "Erika Musterfrau"
    assert mapping["M-102"] == "Max Mustermann"


def test_nachname_allein_nur_bei_eindeutigkeit():
    doppelt = [
        {"id": 1, "vorname": "Anna", "name": "Meier"},
        {"id": 2, "vorname": "Bernd", "name": "Meier"},
    ]
    m = Maskierer(doppelt, nlp=FakeNlp([]))

    maskiert, _ = m.maskiere("Meier stellt den Antrag.", dokument_id=1)

    # Nachname mehrdeutig -> bleibt stehen (nur volle Varianten greifen)
    assert "Meier" in maskiert


def test_nichtmitglieder_ueber_ner(mitglieder):
    m = Maskierer(mitglieder, nlp=FakeNlp(["Hans Besucher"]))
    text = "Gast: Hans Besucher vom Verband. Hans Besucher spricht ein Grußwort."

    maskiert, mapping = m.maskiere(text, dokument_id=55)

    assert "Hans Besucher" not in maskiert
    assert maskiert.count("P-55-1") == 2
    assert mapping["P-55-1"] == "Hans Besucher"


def test_regex_passe_email_telefon_iban(mitglieder):
    m = Maskierer(mitglieder, nlp=FakeNlp([]))
    text = ("Kontakt: erika@example.com, Tel. 0123 123456. "
            "Konto: DE89 3704 0044 0532 0130 00.")

    maskiert, _ = m.maskiere(text, dokument_id=55)

    assert "erika@example.com" not in maskiert
    assert "123456" not in maskiert
    assert "0532" not in maskiert
    assert "[E-MAIL]" in maskiert and "[TELEFON]" in maskiert and "[IBAN]" in maskiert


def test_geburtsdatum_mit_kontext_wird_maskiert(mitglieder):
    """Volle Geburtsdaten sind laut CLAUDE.md verboten — aber nur mit Geburts-
    Kontext maskieren, damit Sitzungsdaten ('Sitzung vom 12.03.2026') erhalten bleiben."""
    m = Maskierer(mitglieder, nlp=FakeNlp([]))
    text = ("Jubilarin, geboren am 15.03.1961. Ehrung bei der Sitzung vom 12.03.2026. "
            "Neuzugang, geb. 01.07.1990.")

    maskiert, _ = m.maskiere(text, dokument_id=55)

    assert "15.03.1961" not in maskiert
    assert "01.07.1990" not in maskiert
    assert maskiert.count("[GEBURTSDATUM]") == 2
    assert "12.03.2026" in maskiert  # Sitzungsdatum bleibt


def test_geburtsdatum_mit_satzzeichen_wird_maskiert(mitglieder):
    """Reale Schreibweisen aus Protokollen und Chat: Doppelpunkt, Fragezeichen,
    'am' erst hinter dem Doppelpunkt. Ohne Satzzeichen-Toleranz rutschen volle
    Geburtsdaten unmaskiert in den Index."""
    m = Maskierer(mitglieder, nlp=FakeNlp([]))
    text = ("Geburtstag? 12.03.1990 — Geburtsdatum: 04.05.1975. "
            "geboren: am 06.07.1980. Geb. 08.09.1985. "
            "Protokoll der Sitzung vom 12.03.2026.")

    maskiert, _ = m.maskiere(text, dokument_id=56)

    for datum in ("12.03.1990", "04.05.1975", "06.07.1980", "08.09.1985"):
        assert datum not in maskiert
    assert maskiert.count("[GEBURTSDATUM]") == 4
    assert "12.03.2026" in maskiert  # Sitzungsdatum bleibt


def test_datum_ohne_geburts_kontext_bleibt(mitglieder):
    """Die Satzzeichen-Toleranz darf nicht dazu führen, dass beliebige Daten
    hinter einem Wort mit 'geb'-Präfix maskiert werden."""
    m = Maskierer(mitglieder, nlp=FakeNlp([]))
    text = "Der Antrag wurde eingereicht. Gebühren fällig ab 01.01.2026."

    maskiert, _ = m.maskiere(text, dokument_id=57)

    assert "01.01.2026" in maskiert
    assert "[GEBURTSDATUM]" not in maskiert


def test_bekannter_fremder_name_wird_ohne_ner_maskiert(mitglieder):
    """Vorbelegte Fremd-Namen (z.B. aus früherem Mapping) werden auch dann
    maskiert, wenn die NER sie in diesem Text nicht erkennt."""
    m = Maskierer(mitglieder, nlp=FakeNlp([]), bekannte_fremde={"Hans Besucher"})

    maskiert, mapping = m.maskiere("Hans Besucher spricht ein Grußwort.", dokument_id=7)

    assert "Hans Besucher" not in maskiert
    assert maskiert.count("P-7-1") == 1
    assert mapping["P-7-1"] == "Hans Besucher"


def test_erkenne_fremde_wirkt_dokumentuebergreifend(mitglieder):
    """Ein per Vorab-Pass erkannter Name wird in JEDEM Dokument maskiert,
    auch wenn die NER ihn dort übersieht."""
    m = Maskierer(mitglieder, nlp=FakeNlpEinmalig(["Hans Besucher"]))

    m.erkenne_fremde("Gast: Hans Besucher vom Verband.")
    maskiert, mapping = m.maskiere("Hans Besucher war erneut anwesend.", dokument_id=9)

    assert "Hans Besucher" not in maskiert
    assert mapping["P-9-1"] == "Hans Besucher"


def test_ner_einzelwoerter_werden_ignoriert(mitglieder):
    """spaCy erkennt massenhaft normale Substantive ("Kassierer", "Kuchen")
    als PER. Nur Mehrwort-Spans zählen als Fremd-Name — Einzelwörter
    bleiben stehen und damit suchbar (Entscheidung Phil, 2026-07-18)."""
    m = Maskierer(mitglieder, nlp=FakeNlp(["Kassierer", "Hans Besucher"]))

    maskiert, mapping = m.maskiere(
        "Der Kassierer begrüßt Hans Besucher.", dokument_id=55)

    assert "Kassierer" in maskiert
    assert "Hans Besucher" not in maskiert
    assert mapping == {"P-55-1": "Hans Besucher"}


def test_ner_spans_mit_kleingeschriebenen_woertern_werden_ignoriert(mitglieder):
    """Spans wie "Mail an" (NER-Fehlerkennung mit Füllwort) sind keine Namen."""
    m = Maskierer(mitglieder, nlp=FakeNlp(["Mail an"]))

    maskiert, mapping = m.maskiere("Bitte Mail an alle senden.", dokument_id=55)

    assert "Mail an" in maskiert
    assert mapping == {}


def test_unplausible_seeds_werden_verworfen(mitglieder):
    """Alte Fehlerkennungen aus der Mapping-Datei (bekannte_fremde) dürfen
    nicht wieder einsickern — derselbe Plausibilitätsfilter wie bei der NER."""
    m = Maskierer(mitglieder, nlp=FakeNlp([]),
                  bekannte_fremde={"Kassierer", "Hans Besucher"})

    maskiert, mapping = m.maskiere(
        "Der Kassierer begrüßt Hans Besucher.", dokument_id=55)

    assert "Kassierer" in maskiert
    assert "Hans Besucher" not in maskiert
    assert mapping == {"P-55-1": "Hans Besucher"}


def test_ner_span_mit_zeilenumbruch_wird_normalisiert(mitglieder):
    """PDF-Extraktion liefert Spans über Zeilenumbrüche ("Hans\\nBesucher").
    Der Kandidat muss auf ein Leerzeichen normalisiert werden (sonst zerreißt
    er die Mapping-Datei) und trotzdem BEIDE Schreibweisen im Text treffen."""
    m = Maskierer(mitglieder, nlp=FakeNlp(["Hans\nBesucher"]))
    text = "Anwesend: Hans\nBesucher. Später begrüßt Hans Besucher die Gäste."

    maskiert, mapping = m.maskiere(text, dokument_id=55)

    assert "Besucher" not in maskiert
    assert maskiert.count("P-55-1") == 2
    assert mapping["P-55-1"] == "Hans Besucher"
    assert "\n" not in mapping["P-55-1"]


def test_mitgliedsname_ueber_zeilenumbruch_wird_maskiert():
    """Auch Stufe 1: 'Anna\\nMeier' (Umbruch mitten im Namen, typisch für
    PDF-Spalten) muss wie 'Anna Meier' maskiert werden. Nachname bewusst
    mehrdeutig, damit nur die volle Namensvariante greifen kann."""
    doppelt = [
        {"id": 1, "vorname": "Anna", "name": "Meier"},
        {"id": 2, "vorname": "Bernd", "name": "Meier"},
    ]
    m = Maskierer(doppelt, nlp=FakeNlp([]))

    maskiert, mapping = m.maskiere("Es begrüßt Anna\nMeier alle.", dokument_id=55)

    assert "Anna" not in maskiert
    assert "M-1" in maskiert
    assert mapping["M-1"] == "Anna Meier"


def test_fremder_name_wird_auch_in_grossschreibung_maskiert(mitglieder):
    """Anwesenheitslisten/Überschriften schreiben Namen oft in Versalien —
    bekannte Fremd-Namen müssen unabhängig von der Schreibweise maskiert werden."""
    m = Maskierer(mitglieder, nlp=FakeNlp([]), bekannte_fremde={"Hans Besucher"})

    maskiert, mapping = m.maskiere("Anwesend: HANS BESUCHER (Verband).", dokument_id=3)

    assert "HANS BESUCHER" not in maskiert
    assert maskiert.count("P-3-1") == 1
    assert mapping["P-3-1"] == "Hans Besucher"
