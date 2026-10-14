"""Tests für die Antwort-Bauer inkl. PII-Sweep über alle Tool-Antworten."""

import json

from webling_mcp import server

# Werte aus den Fixtures, die NIE in einer Tool-Antwort stehen dürfen
VERBOTENE_WERTE = ["Erika", "Musterfrau", "Max", "Mustermann", "Otto",
                   "Ohnedaten", "1961-03-15", "1990-07-01",
                   "2015-04-01", "2021-09-15"]
VERBOTENE_SCHLUESSEL = {"name", "vorname", "email", "adresse", "telefon",
                        "geburtsdatum", "geburtstag",
                        "beitrittsdatum", "beitritt"}


def _alle_schluessel(obj) -> set:
    """Sammelt rekursiv alle Dict-Schlüssel einer Antwort (lowercase-normalisiert)."""
    schluessel = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            schluessel.add(str(k).lower())
            schluessel |= _alle_schluessel(v)
    elif isinstance(obj, list):
        for element in obj:
            schluessel |= _alle_schluessel(element)
    return schluessel


def _alle_antworten(mitglieder) -> list:
    return [
        server.baue_list_members(mitglieder),
        server.baue_list_groups(mitglieder),
        server.baue_beitraege(mitglieder, 2026),
        server.baue_jubilaeen(mitglieder, 2026),
        server.baue_mannschaften(mitglieder),
        server.baue_statistik(mitglieder),
    ]


def test_pii_sweep_ueber_alle_tool_antworten(mitglieder, tmp_output):
    """DER kritische Test: Keine Tool-Antwort enthält Klarnamen oder PII-Felder."""
    for antwort in _alle_antworten(mitglieder):
        text = json.dumps(antwort, ensure_ascii=False)
        for wert in VERBOTENE_WERTE:
            assert wert not in text, f"PII-Leak: '{wert}' in {text[:200]}"
        gefunden = _alle_schluessel(antwort) & VERBOTENE_SCHLUESSEL
        assert not gefunden, f"Verbotene Schlüssel in Antwort: {gefunden}"


def test_baue_list_members_filtert_und_pseudonymisiert(mitglieder):
    antwort = server.baue_list_members(mitglieder, mannschaft="Damen")

    assert antwort["anzahl"] == 1
    assert antwort["mitglieder"][0]["id"] == "M-101"


def test_baue_list_members_meldet_datenabdeckung(mitglieder):
    """Ohne diese Zahl haelt das Modell 'kein Beitrittsjahr' fuer 'nicht lange
    dabei' und benennt beim 'wer ist am laengsten dabei' zuversichtlich den
    Falschen. In Webling ist das Feld bei zwei Dritteln der Mitglieder leer."""
    antwort = server.baue_list_members(mitglieder)

    assert antwort["datenqualitaet"]["beitrittsjahr"] == {"gepflegt": 2, "gesamt": 3}


def test_datenabdeckung_bezieht_sich_auf_die_gefilterte_liste(mitglieder):
    """Die Zahl muss zu den zurueckgegebenen Mitgliedern passen, nicht zum
    Gesamtbestand — sonst rechnet das Modell mit der falschen Grundmenge."""
    antwort = server.baue_list_members(mitglieder, mannschaft="Damen")

    assert antwort["datenqualitaet"]["beitrittsjahr"] == {"gepflegt": 1, "gesamt": 1}


def test_baue_list_groups(mitglieder):
    antwort = server.baue_list_groups(mitglieder)

    assert {"mannschaft": "Damen", "mitglieder": 1} in antwort["gruppen"]
    assert {"mannschaft": "Herren", "mitglieder": 1} in antwort["gruppen"]


def test_baue_beitraege_schreibt_namensliste(mitglieder, tmp_output):
    antwort = server.baue_beitraege(mitglieder, 2026)

    assert antwort["jahr"] == 2026
    assert antwort["anzahl_offen"] == 2
    assert antwort["mitglieder"] == ["M-101", "M-103"]
    # Echte Namen NUR in der lokalen Datei
    inhalt = (tmp_output / "beitraege.md").read_text(encoding="utf-8")
    assert "Erika Musterfrau" in inhalt
    assert antwort["namensliste_lokal"].endswith("beitraege.md")


def test_baue_jubilaeen(mitglieder, tmp_output):
    antwort = server.baue_jubilaeen(mitglieder, 2026)

    assert antwort["anzahl"] == 1
    # KEIN "tag" in der LLM-Antwort: alter + Abfragejahr ergeben das
    # Geburtsjahr — mit Tag UND Monat wäre das volle Geburtsdatum
    # rekonstruierbar (verboten laut CLAUDE.md).
    assert antwort["jubilare"][0] == {"id": "M-101", "alter": 65, "monat": 3}
    # Der genaue Tag steht NUR in der lokalen Datei (neben den Klarnamen)
    inhalt = (tmp_output / "jubilaeen.md").read_text(encoding="utf-8")
    assert "Erika Musterfrau" in inhalt
    assert "am 15.03." in inhalt


def test_baue_mannschaften(mitglieder, tmp_output):
    antwort = server.baue_mannschaften(mitglieder)

    assert antwort["mannschaften"]["Damen"] == [{"id": "M-101", "rang": 1}]
    inhalt = (tmp_output / "mannschaften.md").read_text(encoding="utf-8")
    assert "## Damen" in inhalt
    assert "Erika Musterfrau" in inhalt


def test_baue_statistik(mitglieder):
    antwort = server.baue_statistik(mitglieder)

    assert antwort["statistik"][0]["geburtsjahr"] == 1961


def test_list_members_meldet_status_abdeckung(mitglieder):
    antwort = server.baue_list_members(mitglieder)
    assert antwort["datenqualitaet"]["status"] == {"gepflegt": 2, "gesamt": 3}
