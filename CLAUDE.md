# webling-mcp — Projektregeln

Read-only MCP-Server für die Webling-Vereinsverwaltung eines Sportvereins.
Spec: `docs/superpowers/specs/2026-07-12-webling-mcp-phase-a-design.md`

## Unverhandelbare Regeln

- **Read-only:** `client/http.py` hat NUR `get()`. Keine Schreibfunktionen
  anlegen — auch nicht "für später". Der API-Key hat nur Lese-Rechte.
- **Privacy-Whitelist:** `privacy.py` ist die EINZIGE Stelle, die
  entscheidet, welche Felder ein LLM sieht. Neue Felder für Tool-Antworten
  werden ausschließlich dort freigeschaltet.
- **RAG-Maskierung:** `rag/maskierung.py` ist die einzige Stelle, die
  entscheidet, was vom Dokumenttext ins LLM-Sichtbare gelangt. Der Index
  (`index/`, gitignored) enthält ausschließlich maskierten Text.
- **Verboten in Tool-Antworten:** Name, Vorname, E-Mail, Adresse, Telefon,
  volles Geburtsdatum. Der PII-Sweep-Test
  (`tests/test_server_antworten.py`) erzwingt das.
- **Echte Namen** nur über `privacy.schreibe_namensliste()` in lokale
  Dateien unter `output/` (gitignored, fester Dateiname pro Tool).
- **Kein PII in Logs** — nur Zähler und Fehlertypen.
- **Tests:** nur fiktive Personen, kein Live-API-Zugriff.

## Stil

- Kommentare und Docstrings auf Deutsch
- Kein Overengineering — einfach und funktional
- Konfiguration über `.env` (`WEBLING_BASE_URL`, `WEBLING_MCP_API_KEY`)

## Befehle

- Tests: `venv\Scripts\python -m pytest`
- Server lokal: `venv\Scripts\python -m webling_mcp.server`
- Live-Check (read-only, braucht .env): `venv\Scripts\python scripts/live_check.py`
- Ingest (Dokumente -> Suchindex, braucht .env): `venv\Scripts\python scripts/ingest.py`
- Extraktions-Probe: `venv\Scripts\python scripts/probe_extraktion.py`
