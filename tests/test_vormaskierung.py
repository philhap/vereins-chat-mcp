"""Vormaskierung: Klarnamen in Nutzereingaben -> Pseudonyme (Phase C)."""
from webling_chat.vormaskierung import Vormaskierer

MITGLIEDER = [
    {"id": 1, "vorname": "Timo", "name": "Testmann"},
    {"id": 2, "vorname": "Jenny", "name": "Probefrau"},
    {"id": 3, "vorname": "Karl", "name": "Doppelt"},
    {"id": 4, "vorname": "Karla", "name": "Doppelt"},   # Nachname mehrdeutig
]
FREMDE = {"P-9-1": "Hans Besucher"}


def _vm():
    return Vormaskierer(MITGLIEDER, FREMDE)


def test_vollname_wird_ersetzt():
    assert _vm().maskiere("Hat Timo Testmann bezahlt?") == "Hat M-1 bezahlt?"


def test_case_insensitiv_und_nachname_allein():
    # Eindeutiger Nachname reicht; Handy-Kleinschreibung wird erkannt
    assert _vm().maskiere("was ist mit probefrau?") == "was ist mit M-2?"


def test_mehrdeutiger_nachname_bleibt():
    assert "Doppelt" in _vm().maskiere("Familie Doppelt kommt.")


def test_fremdname_aus_mapping():
    assert _vm().maskiere("Was macht hans besucher?") == "Was macht P-9-1?"


def test_kontaktdaten_werden_entfernt():
    ergebnis = _vm().maskiere("Mail an timo@example.org oder 0123 123456")
    assert "timo@example.org" not in ergebnis and "123456" not in ergebnis


def test_unbekannter_name_bleibt():
    # akzeptiertes Restrisiko wie Phase B
    assert _vm().maskiere("Wer ist Zara Zufall?") == "Wer ist Zara Zufall?"


def test_geburtsdatum_wird_maskiert():
    ergebnis = _vm().maskiere("Zara Zufall, geboren am 12.03.1990, tritt bei.")
    assert "12.03.1990" not in ergebnis
    assert "[GEBURTSDATUM]" in ergebnis


def test_geburtsdatum_mit_satzzeichen_wird_maskiert():
    """Am Handy getippte Fragen sehen so aus — nicht wie Protokolltext."""
    for frage in ("Geburtstag? 12.03.1990 oder?",
                  "Geburtsdatum: 12.03.1990",
                  "geboren: am 12.03.1990"):
        ergebnis = _vm().maskiere(frage)
        assert "12.03.1990" not in ergebnis, frage
        assert "[GEBURTSDATUM]" in ergebnis, frage
