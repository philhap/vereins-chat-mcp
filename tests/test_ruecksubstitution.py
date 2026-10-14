"""Rücksubstitution: Pseudonyme -> Klarnamen für die Anzeige (Phase C)."""
from webling_chat.ruecksubstitution import Ruecksubstituierer

MITGLIEDER = [
    {"id": 1, "vorname": "Timo", "name": "Testmann"},
    {"id": 2, "vorname": "Jenny", "name": "Probefrau"},
]
FREMDE = {"P-9-1": "Hans Besucher", "M-999": "sollte ignoriert werden"}


def _rs():
    return Ruecksubstituierer(MITGLIEDER, FREMDE)


def test_mitglied_und_fremder():
    text = "M-1 hat nicht bezahlt. P-9-1 war Gast."
    assert _rs().ersetze(text) == "Timo Testmann hat nicht bezahlt. Hans Besucher war Gast."


def test_unbekanntes_pseudonym_bleibt():
    assert _rs().ersetze("M-777 fehlt im Mapping.") == "M-777 fehlt im Mapping."


def test_kein_teiltreffer():
    # M-1 darf nicht in "M-10" hineinersetzen
    assert _rs().ersetze("M-10 ist wer anders.") == "M-10 ist wer anders."


def test_m_pseudonyme_kommen_aus_mitgliedern_nicht_aus_mapping():
    # Ein M-Eintrag in der Mapping-Datei darf die Webling-Stammdaten nicht überschreiben
    assert _rs().ersetze("M-999") == "M-999"
