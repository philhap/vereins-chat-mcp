"""
Vormaskierung der Nutzereingabe: bekannte Klarnamen -> Pseudonyme, BEVOR die
Frage an die Anthropic-API geht. Gegenstück zur Rücksubstitution am Ausgang.

Quellen: Mitgliedsnamen aus Webling (dieselbe Varianten-Logik wie
rag/maskierung.py) plus Fremd-Namen aus dem Ingest-Mapping. Namen, die in
keiner Quelle stehen, bleiben stehen — akzeptiertes Restrisiko wie Phase B
(einzelne Vornamen, Tippfehler, unbekannte Personen).
"""

import re

from webling_mcp.rag.maskierung import (
    REGEX_EMAIL, REGEX_IBAN, REGEX_TELEFON, REGEX_GEBURTSDATUM,
    _namensmuster, mitglieder_ersetzungen,
)


class Vormaskierer:
    """Ersetzt bekannte Klarnamen in Freitext durch bestehende Pseudonyme."""

    def __init__(self, mitglieder: list[dict], fremd_mapping: dict[str, str]):
        _, ersetzungen = mitglieder_ersetzungen(mitglieder)
        for pseudo, klarname in fremd_mapping.items():
            if pseudo.startswith("P-"):
                ersetzungen.append((klarname, pseudo))
        ersetzungen.sort(key=lambda e: len(e[0]), reverse=True)
        # Case-insensitiv: am Handy wird klein geschrieben, Autokorrektur variiert
        self._muster = [(_namensmuster(k, re.IGNORECASE), pseudo)
                        for k, pseudo in ersetzungen]

    def maskiere(self, text: str) -> str:
        for muster, pseudo in self._muster:
            text = muster.sub(pseudo, text)
        text = REGEX_EMAIL.sub("[E-MAIL]", text)
        text = REGEX_IBAN.sub("[IBAN]", text)
        text = REGEX_TELEFON.sub("[TELEFON]", text)
        text = REGEX_GEBURTSDATUM.sub(r"\1 [GEBURTSDATUM]", text)
        return text
