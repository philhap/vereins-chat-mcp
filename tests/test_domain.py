"""Tests für die Auswertungslogik."""

from webling_mcp import domain


def test_parse_datum_beide_formate():
    assert domain.parse_datum("1961-03-15").year == 1961
    assert domain.parse_datum("15.03.1961").year == 1961
    assert domain.parse_datum("") is None
    assert domain.parse_datum("kein datum") is None


def test_geburtsjahr(mitglieder):
    assert domain.geburtsjahr(mitglieder[0]) == 1961
    assert domain.geburtsjahr(mitglieder[2]) is None


def test_beitrittsjahr(mitglieder):
    assert domain.beitrittsjahr(mitglieder[0]) == 2015
    assert domain.beitrittsjahr(mitglieder[2]) is None       # Feld leer


def test_datenabdeckung(mitglieder):
    """Zaehlt, bei wie vielen Mitgliedern ein Feld ueberhaupt gepflegt ist."""
    assert domain.datenabdeckung(mitglieder, domain.beitrittsjahr) == {
        "gepflegt": 2, "gesamt": 3}


def test_datenabdeckung_bei_leerer_liste():
    assert domain.datenabdeckung([], domain.beitrittsjahr) == {
        "gepflegt": 0, "gesamt": 0}


def test_beitrittsjahr_bei_unbrauchbarem_datum():
    # In Webling ist "Beitritt" oft nicht gepflegt - kaputte Werte duerfen
    # nicht durchschlagen, sondern muessen wie "unbekannt" aussehen
    assert domain.beitrittsjahr({"beitrittsdatum": "keine Angabe"}) is None
    assert domain.beitrittsjahr({}) is None


def test_filtere_unbezahlt(mitglieder):
    offen = domain.filtere_unbezahlt(mitglieder, 2026)

    # Erika (2025 < 2026) und Otto ("" -> 0 < 2026), Max hat bezahlt
    assert [m["id"] for m in offen] == [101, 103]  # sortiert nach Name


def test_filtere_jubilaeen(mitglieder):
    # Erika wird 2026 genau 65 -> Jubiläum; Max wird 36 -> kein Jubiläum
    jubilare = domain.filtere_jubilaeen(mitglieder, 2026)

    assert len(jubilare) == 1
    assert jubilare[0]["id"] == 101
    assert jubilare[0]["alter"] == 65
    assert jubilare[0]["monat"] == 3
    assert jubilare[0]["tag"] == 15


def test_filtere_jubilaeen_kein_treffer_bei_64(mitglieder):
    assert domain.filtere_jubilaeen(mitglieder, 2025) == []


def test_gruppiere_nach_mannschaft(mitglieder):
    gruppen = domain.gruppiere_nach_mannschaft(mitglieder)

    # Otto ohne Mannschaft wird ignoriert
    assert set(gruppen.keys()) == {"Damen", "Herren"}
    assert gruppen["Damen"][0]["id"] == 101


def test_gruppiere_sortiert_nach_rang():
    spieler = [
        {"id": 1, "mannschaft": "Herren", "rang": None},
        {"id": 2, "mannschaft": "Herren", "rang": 3},
        {"id": 3, "mannschaft": "Herren", "rang": 1},
    ]
    gruppen = domain.gruppiere_nach_mannschaft(spieler)

    assert [s["id"] for s in gruppen["Herren"]] == [3, 2, 1]  # None ans Ende


def test_statistik_nach_geburtsjahr(mitglieder):
    statistik = domain.statistik_nach_geburtsjahr(mitglieder)

    assert statistik == [
        {"geburtsjahr": 1961, "maennlich": 0, "weiblich": 1, "gesamt": 1},
        {"geburtsjahr": 1990, "maennlich": 1, "weiblich": 0, "gesamt": 1},
    ]


def test_statistik_zaehlt_ohne_geschlecht_ins_gesamt():
    mitglieder = [
        {"id": 1, "geburtsdatum": "1970-01-01", "geschlecht": "m"},
        {"id": 2, "geburtsdatum": "1970-06-15", "geschlecht": ""},
    ]
    statistik = domain.statistik_nach_geburtsjahr(mitglieder)

    assert statistik == [
        {"geburtsjahr": 1970, "maennlich": 1, "weiblich": 0, "gesamt": 2},
    ]


def test_filtere_mitglieder_nach_mannschaft(mitglieder):
    ergebnis = domain.filtere_mitglieder(mitglieder, mannschaft="Damen")
    assert [m["id"] for m in ergebnis] == [101]


def test_filtere_mitglieder_nach_geburtsjahr(mitglieder):
    ergebnis = domain.filtere_mitglieder(mitglieder, geburtsjahr_von=1980)
    # Otto ohne Geburtsdatum fällt bei Jahresfiltern raus
    assert [m["id"] for m in ergebnis] == [102]


def test_filtere_mitglieder_ohne_filter(mitglieder):
    assert len(domain.filtere_mitglieder(mitglieder)) == 3


def test_mitgliedsbeitrag_je_kategorie():
    # Jeder Code aus der Ordnung liefert seinen Betrag
    for code, (_bedeutung, betrag) in domain.BEITRAGSORDNUNG.items():
        assert domain.mitgliedsbeitrag({"status": code}) == betrag


def test_mitgliedsbeitrag_stichproben():
    assert domain.mitgliedsbeitrag({"status": "A-Mitglied"}) == 150
    assert domain.mitgliedsbeitrag({"status": "P-Mitglied"}) == 20
    assert domain.mitgliedsbeitrag({"status": "C-Mitglied"}) == 300
    assert domain.mitgliedsbeitrag({"status": "Ehrenmitglied"}) == 0


def test_mitgliedsbeitrag_leer_und_unbekannt_ist_none():
    assert domain.mitgliedsbeitrag({"status": ""}) is None
    assert domain.mitgliedsbeitrag({}) is None
    assert domain.mitgliedsbeitrag({"status": "X-Mitglied"}) is None


def test_status_kategorie(mitglieder):
    assert domain.status_kategorie(mitglieder[0]) == "A-Mitglied"
    assert domain.status_kategorie(mitglieder[2]) is None  # status ""


def test_datenabdeckung_status(mitglieder):
    # Erika + Max haben Status, Otto nicht
    assert domain.datenabdeckung(mitglieder, domain.status_kategorie) == {
        "gepflegt": 2, "gesamt": 3}


def test_status_legende_enthaelt_jeden_code_mit_betrag():
    legende = domain.status_legende()
    for code, (bedeutung, betrag) in domain.BEITRAGSORDNUNG.items():
        assert code in legende
        assert bedeutung in legende
        assert f"({betrag} €/Jahr)" in legende


def _m(mid, status, geburtsjahr):
    return {"id": mid, "status": status, "geburtsdatum": f"{geburtsjahr}-06-01"}


def test_status_widersprueche_kind_als_c():
    # 12 Jahre (Geburtsjahr 2014), C-Mitglied = erwachsen -> Widerspruch
    ausreisser = domain.status_widersprueche([_m(1, "C-Mitglied", 2014)], 2026)
    assert len(ausreisser) == 1
    assert ausreisser[0]["id"] == 1
    assert ausreisser[0]["alter"] == 11  # 2026 - 2014 - 1


def test_status_widersprueche_18_wird_dieses_jahr_zaehlt_als_unter_18():
    # Geburtsjahr 2008 -> wird 2026 achtzehn -> zaehlt als 17 -> A ist Widerspruch
    ausreisser = domain.status_widersprueche([_m(1, "A-Mitglied", 2008)], 2026)
    assert len(ausreisser) == 1
    assert ausreisser[0]["alter"] == 17


def test_status_widersprueche_erwachsener_ist_ok():
    assert domain.status_widersprueche([_m(1, "A-Mitglied", 1980)], 2026) == []


def test_status_widersprueche_f_und_e_grenzen():
    # F = bis 12: Geburtsjahr 2012 -> alter 13 -> Widerspruch
    assert domain.status_widersprueche([_m(1, "F-Mitglied", 2012)], 2026) != []
    # E = 13-18: Geburtsjahr 2010 -> alter 15 -> ok
    assert domain.status_widersprueche([_m(1, "E-Mitglied", 2010)], 2026) == []
    # E mit alter 19 (Geburtsjahr 2006 -> 2026-2006-1=19) -> Widerspruch
    assert domain.status_widersprueche([_m(1, "E-Mitglied", 2006)], 2026) != []


def test_status_widersprueche_p_ca_ehren_ohne_altersregel():
    for status in ("P-Mitglied", "CA-Mitglied (Familienangehöriger)", "Ehrenmitglied"):
        assert domain.status_widersprueche([_m(1, status, 2018)], 2026) == []


def test_status_widersprueche_ueberspringt_ohne_geburtsjahr():
    m = {"id": 1, "status": "C-Mitglied", "geburtsdatum": ""}
    assert domain.status_widersprueche([m], 2026) == []
