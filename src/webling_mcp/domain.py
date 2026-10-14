"""
Auswertungslogik auf normalisierten Mitgliederdaten.
Arbeitet auf UNpseudonymisierten Daten — die Pseudonymisierung passiert
erst an der Tool-Grenze (server.py via privacy.py).
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def parse_datum(datum_str: str) -> datetime | None:
    """Parst YYYY-MM-DD (Webling) oder DD.MM.YYYY."""
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(datum_str.strip(), fmt)
        except ValueError:
            continue
    return None


def geburtsjahr(mitglied: dict) -> int | None:
    """Geburtsjahr eines Mitglieds oder None."""
    geb = parse_datum(mitglied.get("geburtsdatum", ""))
    return geb.year if geb else None


def datenabdeckung(mitglieder: list[dict], feld) -> dict:
    """Wie viele Mitglieder haben dieses Feld überhaupt gepflegt?

    Geht an das LLM mit, damit es Lücken benennen kann statt sie zu übersehen:
    fehlende Werte sehen sonst aus wie „trifft nicht zu" statt „unbekannt".
    `feld` ist eine Funktion wie geburtsjahr oder beitrittsjahr.
    """
    return {
        "gepflegt": sum(1 for m in mitglieder if feld(m) is not None),
        "gesamt": len(mitglieder),
    }


def beitrittsjahr(mitglied: dict) -> int | None:
    """Beitrittsjahr eines Mitglieds oder None. Nur das Jahr geht an das LLM —
    das exakte Datum wäre in einem kleinen Verein ein Wiedererkennungsmerkmal."""
    beitritt = parse_datum(mitglied.get("beitrittsdatum", ""))
    return beitritt.year if beitritt else None


def filtere_mitglieder(
    mitglieder: list[dict],
    mannschaft: str | None = None,
    geburtsjahr_von: int | None = None,
    geburtsjahr_bis: int | None = None,
) -> list[dict]:
    """Filtert nach Mannschaft und/oder Geburtsjahr-Bereich."""
    ergebnis = []
    for m in mitglieder:
        if mannschaft and m.get("mannschaft") != mannschaft:
            continue
        jahr = geburtsjahr(m)
        if geburtsjahr_von is not None and (jahr is None or jahr < geburtsjahr_von):
            continue
        if geburtsjahr_bis is not None and (jahr is None or jahr > geburtsjahr_bis):
            continue
        ergebnis.append(m)
    return ergebnis


def filtere_unbezahlt(mitglieder: list[dict], jahr: int) -> list[dict]:
    """Mitglieder mit Beitragsstatus < jahr, sortiert nach Name."""
    offen = []
    for m in mitglieder:
        try:
            bezahlt_bis = int(m.get("beitragsstatus") or 0)
        except (ValueError, TypeError):
            bezahlt_bis = 0
        if bezahlt_bis < jahr:
            offen.append(m)
    offen.sort(key=lambda m: (m.get("name", ""), m.get("vorname", "")))
    return offen


def filtere_jubilaeen(mitglieder: list[dict], jahr: int) -> list[dict]:
    """
    Mitglieder, die im Zieljahr 65, 70, 75, 80, ... werden.
    Ergänzt 'alter', 'monat' und 'tag', sortiert nach Monat und Tag.
    """
    jubilare = []
    for m in mitglieder:
        geb = parse_datum(m.get("geburtsdatum", ""))
        if not geb:
            continue
        alter = jahr - geb.year
        if alter >= 65 and alter % 5 == 0:
            eintrag = dict(m)
            eintrag["alter"] = alter
            eintrag["monat"] = geb.month
            eintrag["tag"] = geb.day
            jubilare.append(eintrag)
    jubilare.sort(key=lambda m: (m["monat"], m["tag"]))
    return jubilare


def gruppiere_nach_mannschaft(mitglieder: list[dict]) -> dict[str, list[dict]]:
    """Gruppiert nach Mannschaft (ohne Mannschaft -> ignoriert), sortiert nach Rang."""
    gruppen: dict[str, list[dict]] = {}
    for m in mitglieder:
        mannschaft = (m.get("mannschaft") or "").strip()
        if not mannschaft:
            continue
        gruppen.setdefault(mannschaft, []).append(m)
    for spieler in gruppen.values():
        spieler.sort(key=lambda s: (not isinstance(s.get("rang"), int),
                                    s.get("rang") if isinstance(s.get("rang"), int) else 0))
    return gruppen


def statistik_nach_geburtsjahr(mitglieder: list[dict]) -> list[dict]:
    """Zählt Mitglieder pro Geburtsjahr, aufgeteilt nach Geschlecht.

    'gesamt' zählt ALLE Mitglieder des Jahrgangs — auch ohne Geschlechtsangabe.
    """
    zaehler: dict[int, dict[str, int]] = {}
    for m in mitglieder:
        jahr = geburtsjahr(m)
        if jahr is None:
            continue
        eintrag = zaehler.setdefault(jahr, {"m": 0, "w": 0, "gesamt": 0})
        eintrag["gesamt"] += 1
        geschlecht = m.get("geschlecht", "")
        if geschlecht in ("m", "w"):
            eintrag[geschlecht] += 1
    return [
        {
            "geburtsjahr": jahr,
            "maennlich": z["m"],
            "weiblich": z["w"],
            "gesamt": z["gesamt"],
        }
        for jahr, z in sorted(zaehler.items())
    ]


# Beitragsordnung — die EINZIGE Quelle: Status-Code -> (Bedeutung, Jahresbeitrag).
# Sowohl der abgeleitete Beitrag als auch die LLM-Legende kommen von hier.
# Schluessel ist der exakte Webling-Wert (inkl. Klammerzusatz bei CA).
BEITRAGSORDNUNG: dict[str, tuple[str, int]] = {
    "A-Mitglied":  ("Aktiv", 150),
    "P-Mitglied":  ("Passiv", 20),
    "B-Mitglied":  ("Ehegatte/Partner eines A-Mitglieds", 100),
    "C-Mitglied":  ("Familie (2 aktive Erwachsene + Kinder U18)", 300),
    "D-Mitglied":  ("Schüler/Student ab 18", 60),
    "E-Mitglied":  ("Jugendliche 13–18", 40),
    "F-Mitglied":  ("Kinder bis 12", 30),
    "CA-Mitglied (Familienangehöriger)": ("Familienangehöriger", 0),
    "Ehrenmitglied": ("Ehrenmitglied", 0),
}


def mitgliedsbeitrag(mitglied: dict) -> int | None:
    """Jahresbeitrag, aus dem Status abgeleitet (feste Beitragsordnung).

    Nicht aus dem Webling-Feld 'Mitgliedsbeitrag' gelesen (dort unzuverlaessig).
    Leerer oder unbekannter Status -> None: nie einen Betrag raten.
    """
    status = mitglied.get("status") or ""
    eintrag = BEITRAGSORDNUNG.get(status)
    if eintrag is None:
        if status:
            logger.warning("Unbekannter Status ohne Beitragszuordnung: %r", status)
        return None
    return eintrag[1]


def status_kategorie(mitglied: dict) -> str | None:
    """Status-Kategorie oder None — Adapter fuer datenabdeckung()."""
    return mitglied.get("status") or None


def status_legende() -> str:
    """Legendentext fuer den System-Prompt, aus BEITRAGSORDNUNG erzeugt —
    eine Quelle fuer Ableitung und Legende, kein Auseinanderlaufen."""
    return "\n".join(
        f"  - {code}: {bedeutung} ({betrag} €/Jahr)"
        for code, (bedeutung, betrag) in BEITRAGSORDNUNG.items()
    )


# Muss mit BEITRAGSORDNUNG synchron gehalten werden: neue Kategorien dort erfordern
# Update hier. Keine Test deckt diesen Drift automatisch ab.
# Erwachsenen-Kategorien: ab 18. Jugend-/Kinderkategorien mit eigener Grenze.
_ERWACHSEN = ("A-Mitglied", "B-Mitglied", "C-Mitglied", "D-Mitglied")


def _altersregel_verletzt(status: str, alter: int) -> str | None:
    """Grund, wenn Alter klar nicht zur Kategorie passt, sonst None."""
    if status == "F-Mitglied" and alter > 12:
        return f"Alter {alter} passt nicht zu F-Mitglied (Kinder bis 12)"
    if status == "E-Mitglied" and not (13 <= alter <= 18):
        return f"Alter {alter} passt nicht zu E-Mitglied (Jugendliche 13–18)"
    if status in _ERWACHSEN and alter < 18:
        return f"Alter {alter} passt nicht zu {status} (erwartet ab 18)"
    return None


def status_widersprueche(mitglieder: list[dict], jahr: int) -> list[dict]:
    """Mitglieder, deren Alter nicht zur Status-Kategorie passt.

    Maßgebliches Alter = jahr - geburtsjahr - 1: wer im laufenden Jahr X wird,
    zaehlt noch als „unter X". Bewusst anders als die Jubilaeumslogik
    (dort jahr - geburtsjahr, weil man im Jahr X „X wird"). P/CA/Ehrenmitglied
    haben keine Altersregel; Mitglieder ohne Geburtsjahr werden uebersprungen.
    """
    ausreisser = []
    for m in mitglieder:
        gj = geburtsjahr(m)
        status = m.get("status") or ""
        if gj is None or not status:
            continue
        alter = jahr - gj - 1
        grund = _altersregel_verletzt(status, alter)
        if grund:
            ausreisser.append({"id": m["id"], "status": status,
                               "alter": alter, "grund": grund})
    return ausreisser
