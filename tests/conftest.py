"""Gemeinsame Test-Fixtures. Nur fiktive Personen!"""

import pytest


@pytest.fixture
def mitglieder():
    """Drei fiktive Mitglieder in interner (unpseudonymisierter) Darstellung."""
    return [
        {"id": 101, "vorname": "Erika", "name": "Musterfrau",
         "geburtsdatum": "1961-03-15", "beitrittsdatum": "2015-04-01",
         "geschlecht": "w",
         "mannschaft": "Damen", "rang": 1, "beitragsstatus": "2025",
         "status": "A-Mitglied"},
        {"id": 102, "vorname": "Max", "name": "Mustermann",
         "geburtsdatum": "1990-07-01", "beitrittsdatum": "2021-09-15",
         "geschlecht": "m",
         "mannschaft": "Herren", "rang": 2, "beitragsstatus": "2026",
         "status": "P-Mitglied"},
        {"id": 103, "vorname": "Otto", "name": "Ohnedaten",
         "geburtsdatum": "", "beitrittsdatum": "", "geschlecht": "m",
         "mannschaft": "", "rang": None, "beitragsstatus": "",
         "status": ""},
    ]


@pytest.fixture
def tmp_output(tmp_path, monkeypatch):
    """Lenkt privacy.OUTPUT_DIR in ein Temp-Verzeichnis um."""
    from webling_mcp import privacy

    ziel = tmp_path / "output"
    monkeypatch.setattr(privacy, "OUTPUT_DIR", ziel)
    return ziel


@pytest.fixture
def tmp_index(tmp_path, monkeypatch):
    """Lenkt den RAG-Index in ein Temp-Verzeichnis um."""
    from webling_mcp.rag import index

    ziel = tmp_path / "index"
    monkeypatch.setattr(index, "INDEX_DIR", ziel)
    return ziel
