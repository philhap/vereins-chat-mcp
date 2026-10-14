"""Tests für die Privacy-Schicht (Whitelist-Pseudonymisierung, lokales Rendern)."""

import pytest

from webling_mcp import privacy

ERLAUBTE_FELDER = {"id", "geburtsjahr", "beitrittsjahr", "geschlecht",
                   "mannschaft", "rang", "beitragsstatus",
                   "status", "mitgliedsbeitrag"}


def test_pseudonymisiere_enthaelt_nur_whitelist_felder(mitglieder):
    ergebnis = privacy.pseudonymisiere(mitglieder[0])

    assert set(ergebnis.keys()) == ERLAUBTE_FELDER


def test_pseudonymisiere_werte(mitglieder):
    ergebnis = privacy.pseudonymisiere(mitglieder[0])

    assert ergebnis["id"] == "M-101"
    assert ergebnis["geburtsjahr"] == 1961
    assert ergebnis["geschlecht"] == "w"
    assert ergebnis["mannschaft"] == "Damen"
    assert ergebnis["rang"] == 1
    assert ergebnis["beitragsstatus"] == "2025"


def test_pseudonymisiere_ohne_geburtsdatum(mitglieder):
    assert privacy.pseudonymisiere(mitglieder[2])["geburtsjahr"] is None


def test_pseudonymisiere_beitritt_nur_als_jahr(mitglieder):
    """Wie beim Geburtstag: das Jahr genügt für 'seit wann dabei', das exakte
    Datum wäre in einem 95-Mitglieder-Verein ein starker Wiedererkennungs-
    Marker."""
    ergebnis = privacy.pseudonymisiere(mitglieder[0])

    assert ergebnis["beitrittsjahr"] == 2015
    assert "2015-04-01" not in str(ergebnis)


def test_pseudonymisiere_ohne_beitrittsdatum(mitglieder):
    assert privacy.pseudonymisiere(mitglieder[2])["beitrittsjahr"] is None


def test_keine_klarnamen_in_pseudonymisierter_ausgabe(mitglieder):
    text = str(privacy.pseudonymisiere(mitglieder[0]))

    assert "Erika" not in text
    assert "Musterfrau" not in text
    assert "1961-03-15" not in text  # volles Geburtsdatum bleibt lokal


def test_pseudonym():
    assert privacy.pseudonym({"id": 42}) == "M-42"


def test_schreibe_namensliste(tmp_output):
    pfad = privacy.schreibe_namensliste(
        "beitraege.md", "Unbezahlte Beiträge 2026", ["- Erika Musterfrau"]
    )

    assert pfad.endswith("beitraege.md")
    inhalt = (tmp_output / "beitraege.md").read_text(encoding="utf-8")
    assert "# Unbezahlte Beiträge 2026" in inhalt
    assert "- Erika Musterfrau" in inhalt


def test_schreibe_namensliste_ueberschreibt(tmp_output):
    """Fester Dateiname pro Tool: alte PII-Dateien sammeln sich nicht an."""
    privacy.schreibe_namensliste("beitraege.md", "Alt", ["- Alter Eintrag"])
    privacy.schreibe_namensliste("beitraege.md", "Neu", ["- Neuer Eintrag"])

    inhalt = (tmp_output / "beitraege.md").read_text(encoding="utf-8")
    assert "Alter Eintrag" not in inhalt
    assert "Neuer Eintrag" in inhalt


def test_schreibe_namensliste_verweigert_traversal(tmp_output):
    with pytest.raises(ValueError):
        privacy.schreibe_namensliste("..\\boese.md", "Titel", ["- x"])


def test_schreibe_namensliste_verweigert_fremde_dateinamen(tmp_output):
    with pytest.raises(ValueError):
        privacy.schreibe_namensliste("C:\\temp\\evil.md", "Titel", ["- x"])


def test_pseudonymisiere_status_und_beitrag(mitglieder):
    ergebnis = privacy.pseudonymisiere(mitglieder[0])  # Erika, A-Mitglied
    assert ergebnis["status"] == "A-Mitglied"
    assert ergebnis["mitgliedsbeitrag"] == 150


def test_pseudonymisiere_beitrag_none_ohne_status(mitglieder):
    ergebnis = privacy.pseudonymisiere(mitglieder[2])  # Otto, status ""
    assert ergebnis["status"] == ""
    assert ergebnis["mitgliedsbeitrag"] is None


def test_schreibe_namensliste_erlaubt_status_pruefung(tmp_output):
    pfad = privacy.schreibe_namensliste(
        "status_pruefung.md", "Status-Prüfung 2026", ["- Max Mustermann (M-1)"]
    )
    assert pfad.endswith("status_pruefung.md")
    inhalt = (tmp_output / "status_pruefung.md").read_text(encoding="utf-8")
    assert "Max Mustermann" in inhalt
