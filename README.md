# webling-mcp

Read-only MCP-Server und Chat-App für die Vereinsverwaltung [Webling](https://www.webling.ch).
Mitgliederdaten werden pseudonymisiert, bevor sie ein Sprachmodell erreichen.
Gebaut für einen Sportverein und dort im Einsatz.

> **In English:** A read-only MCP server and chat web app for a sports club's
> member database. Every tool response is built from a field whitelist, so the
> language model only ever sees pseudonyms. Real names are swapped back in on
> the way out, between server and browser. 187 tests enforce that no personal
> data reaches the model API.

## Das Problem

Ein Vereinsvorstand will fragen können: „Wer hat noch nicht bezahlt?" oder
„Wer hat dieses Jahr ein rundes Jubiläum?". Ein Sprachmodell beantwortet das
gut. Aber jede Tool-Antwort läuft durch die API eines Drittanbieters, und
Klarnamen von Mitgliedern haben dort nach DSGVO nichts verloren.

## Die Lösung: Das Modell sieht nie einen Namen

Jede Anfrage durchläuft drei Stufen.

| Stufe | Was passiert | Code |
|---|---|---|
| Eingang | Bekannte Namen in der Frage werden durch Pseudonyme ersetzt, bevor die Frage an die API geht | `webling_chat/vormaskierung.py` |
| Verarbeitung | Tool-Antworten entstehen aus einer Feld-Whitelist. Das Modell bekommt Pseudonyme (`M-1234`) und Aggregate, nie Name, Adresse, E-Mail, Telefon oder volles Geburtsdatum | `webling_mcp/privacy.py` |
| Ausgang | Pseudonyme in der fertigen Antwort werden erst auf dem Weg zum Browser zu Klarnamen aufgelöst | `webling_chat/ruecksubstitution.py` |

Die Whitelist ist konstruktiv: Antworten werden aus erlaubten Feldern
aufgebaut, statt verbotene herauszufiltern. Ein neues Feld in Webling kann
deshalb nicht versehentlich durchrutschen. Ein PII-Sweep-Test prüft jede
Tool-Antwort.

Im lokalen Einsatz mit Claude Code gibt es einen zweiten Ausgabekanal:
Namenslisten wie Mahnliste, Jubiläen und Aufstellungen landen als
Markdown-Datei unter `output/` und verlassen den Rechner nie.

## Komponenten

    src/
    ├── webling_mcp/            MCP-Server (FastMCP, stdio)
    │   ├── server.py           Einstieg, Fehlerbehandlung
    │   ├── tools.py            10 Tools, auch von der Chat-App genutzt
    │   ├── privacy.py          Feld-Whitelist, einzige Stelle für Freigaben
    │   ├── domain.py           Auswertungen: Beiträge, Jubiläen, Statistik
    │   ├── client/             Webling-API-Client, nur GET
    │   └── rag/                Dokumentensuche, Maskierung beim Indexieren
    └── webling_chat/           Chat-PWA (FastAPI)
        ├── app.py              Web-App, Login, Streaming
        ├── chat.py             Tool-Use-Schleife gegen die Anthropic-API
        ├── auth.py             Argon2id, serverseitige Sessions, Rate-Limit
        ├── policy.py           welche Rolle welche Tools sieht
        ├── vormaskierung.py    Namen raus, bevor die Frage die API erreicht
        └── ruecksubstitution.py  Namen zurück, auf dem Weg zum Browser

## Tools

| Tool | Beschreibung |
|---|---|
| `list_members` | Mitglieder (pseudonymisiert) mit Status, Beitrag und Beitrittsjahr, filterbar nach Mannschaft und Geburtsjahr |
| `get_member` | Einzelmitglied per Pseudonym `M-<id>` |
| `list_groups` | Mannschaften mit Mitgliederzahl |
| `list_documents` | Dateinamen im Jahresordner |
| `unbezahlte_beitraege` | Mahnliste, Namen nur in lokaler Datei |
| `jubilaeen` | Runde Geburtstage, Namen nur in lokaler Datei |
| `mannschaften` | Aufstellungen mit Rang, Namen nur in lokaler Datei |
| `mitglieder_statistik` | Statistik nach Geburtsjahr und Geschlecht |
| `suche_dokumente` | Hybridsuche über maskierte Vereinsdokumente |
| `lies_dokument` | Maskierter Volltext eines indexierten Dokuments |

## Mitgliedsstatus und Beitrag

Das Modell sieht die Mitgliedskategorie und den Jahresbeitrag. Den Beitrag
rechnet aber nicht das Modell, sondern der Server, deterministisch aus einer
festen Beitragsordnung.

Das Webling-Feld für den Beitrag wird bewusst nicht gelesen. Ein Abgleich
mit echten Daten zeigte Leerwerte und Beträge, die nicht zur Kategorie
passten. Und bei Geld ist eine plausible Falschauskunft teuer, während sich
Modell-Arithmetik nicht testen lässt.

Ein Konsistenz-Check (`scripts/status_check.py`) findet Mitglieder, deren
Alter nicht zur Kategorie passt. Die Konsole zeigt dabei nur Pseudonyme.

Tool-Antworten melden außerdem die Datenabdeckung, etwa wie viele Mitglieder
einen gepflegten Status haben. So kann das Modell sagen, wenn eine
Auswertung auf unvollständigen Daten beruht, statt sie als vollständig
auszugeben.

## Dokumentensuche

Hybridsuche (BM25 plus lokale Embeddings, Reciprocal Rank Fusion) über
Satzung, Ordnungen, Protokolle und Finanzberichte. Personenbezogene Daten werden **beim
Indexieren** maskiert (`rag/maskierung.py`):

- Mitglieder deterministisch über die Mitgliederliste (`M-<id>`, wie in den Tools)
- Nicht-Mitglieder per spaCy-NER (`P-<Dok>-<n>`)
- E-Mail, Telefon und IBAN per Regex

Der Index (SQLite FTS5 plus sqlite-vec) enthält dadurch nie Klarnamen.
Embedding-Modell: `intfloat/multilingual-e5-small`, lokal auf der CPU.

Ingest anstoßen, wenn neue Dokumente in Webling liegen:

    venv\Scripts\python scripts/ingest.py

## Chat-App

Installierbare Web-App mit Login und Streaming-Antworten. Läuft als
FastAPI-App hinter einem HTTPS-Reverse-Proxy auf einem VPS.

- Ein Konto pro Person, Passwörter mit Argon2id, kein Selbst-Registrieren
- Sessions serverseitig und einzeln widerrufbar
- Vorgeschaltete Basic Auth hält Bots und Rateversuche vom eigentlichen Login fern
- Rollenmodell in `policy.py`: Neue Rollen sind eine Datenänderung, kein Umbau
- Der Gesprächsverlauf bleibt serverseitig und pseudonym

Betrieb: [VPS-Betriebsanleitung](docs/betrieb-vps.md)

## Qualitätssicherung

- 187 Tests, alle mit fiktiven Personen und ohne Zugriff auf die echte API
- PII-Sweep: Jede Tool-Antwort wird auf verbotene Felder geprüft
- PII-Stichprobe am echten Index (`scripts/pii_stichprobe.py`): prüft, dass
  kein Klarname aus dem Pseudonym-Mapping im Suchindex steht. Die Konsole
  zeigt nur Zähler.
- Read-only ist testgesichert: Der API-Client kennt nur `get()`

## Designentscheidungen

Jede Ausbaustufe hat eine eigene Spec, jeweils mit den verworfenen
Alternativen und dem Grund dafür.

- [Phase A: MCP-Server und Privacy-Layer](docs/superpowers/specs/2026-07-12-webling-mcp-phase-a-design.md)
- [Phase B: Dokumentensuche](docs/superpowers/specs/2026-07-16-webling-mcp-phase-b-rag-design.md)
- [Phase C: Chat-App](docs/superpowers/specs/2026-07-18-webling-chat-phase-c-design.md)
- [Mitgliedsstatus und Beitragsableitung](docs/superpowers/specs/2026-07-22-webling-status-beitrag-design.md)

## Setup

    python -m venv venv
    venv\Scripts\python -m pip install -e ".[dev]"
    copy .env.example .env   # API-Key eintragen, nur Lese-Rechte
    venv\Scripts\python -m pytest

Registrierung in Claude Code (`.mcp.json` im Projekt- oder Parent-Ordner):

    {
      "mcpServers": {
        "webling": {
          "command": "<absoluter-pfad>/webling-mcp/venv/Scripts/python.exe",
          "args": ["-m", "webling_mcp.server"]
        }
      }
    }

## Sicherheit

- API-Key mit **nur Lese-Rechten**. Der Server kann nichts schreiben, der
  Code enthält keine Schreiboperationen.
- Keine Persistierung von Mitgliederdaten im MCP-Server, kein Cache
- Kein PII in Logs, nur Zähler und Fehlertypen

## Lizenz

MIT, siehe [LICENSE](LICENSE).
