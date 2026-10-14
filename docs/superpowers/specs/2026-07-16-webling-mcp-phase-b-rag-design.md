# webling-mcp — Phase B Design: RAG-Layer

**Datum:** 2026-07-16
**Status:** Entwurf validiert (Brainstorming-Session mit Phil)
**Projekt:** webling-mcp Phase B — Hybridsuche über Vereinsdokumente
**Voraussetzung:** Phase A abgeschlossen (8 Tools, Privacy-Layer, E2E-Test bestanden 2026-07-16)

---

## Kontext & Ziel

Phase A macht Webling-**Mitgliederdaten** pseudonymisiert für Claude nutzbar.
Phase B erweitert das um die **Dokumente** des Vereins: Satzung, Ordnungen und
Sitzungsprotokolle — alle liegen in Webling-Dokumentordnern. Ziel sind Fragen
wie „Was steht in der Satzung zu Kündigungsfristen?" oder „Was haben wir 2025
zur Beitragserhöhung beschlossen?", beantwortet in natürlicher Sprache mit
Quellenangabe.

**Primärer Konsument:** Phil über Claude Code / Claude Desktop (wie Phase A).

## Entscheidungen (aus Brainstorming 2026-07-16)

| Thema | Entscheidung |
|---|---|
| Scope | Nur RAG. Klarnamen-im-Chat (lokales LLM / Bedrock EU) wird eine eigene spätere Phase |
| Quellen | Webling-Dokumentordner (Satzung, Ordnungen, Protokolle) — einzige Quelle, keine Obsidian-Notizen |
| Korpusgröße | ~50–200 Dokumente → leichter lokaler Index, kein schweres Setup |
| PII-Strategie | Maskierung **beim Indexieren** — der Index enthält nie Klarnamen |
| Restrisiko | Best-Effort-Maskierung von Phil als Vorstand akzeptiert (2026-07-16) |
| Suchtechnik | Hybridsuche: BM25 (SQLite FTS5) + lokale Embeddings, Fusion per RRF |
| Embeddings | `intfloat/multilingual-e5-small` via sentence-transformers, lokal auf CPU |
| Speicher | Eine SQLite-Datei in `index/` (FTS5 + sqlite-vec), gitignored |
| Ingest | Manuelles Skript, kein Automatismus |

## Nicht-Ziele (Phase B)

- Kein OCR für gescannte PDFs (Dokumente ohne Textebene werden übersprungen und gemeldet)
- Keine automatische Rück-Übersetzung von Pseudonymen im Chat (→ Klarnamen-Phase)
- Kein automatischer/geplanter Ingest
- Keine Obsidian-Notizen als Quelle
- Kein Reranking-Modell (bei ~200 Dokumenten unnötig; nachrüstbar, falls Trefferqualität enttäuscht)
- Kein Policy-/Auth-Layer (bleibt Phase C)
- Kein Hosting auf einem Server — der Stack bleibt lokal (siehe Privacy-Design)

---

## Architektur

Phase B ergänzt das bestehende Package, ohne Phase-A-Schichten anzufassen:

```
webling-mcp/
├── src/webling_mcp/
│   ├── client/              # Phase A, read-only
│   │   └── documents.py     # + Download von Dokumentinhalten (neu, nur GET)
│   ├── privacy.py           # Phase A, unverändert (Mitglieder-Whitelist)
│   ├── rag/                 # NEU
│   │   ├── ingest.py        #   Pipeline: Sync → Extraktion → Maskierung → Index
│   │   ├── maskierung.py    #   PII-Maskierung (einzige Entscheidungsstelle)
│   │   ├── extraktion.py    #   PDF (pypdf) / Word (python-docx) → Text
│   │   └── suche.py         #   Hybridsuche: FTS5 + Embeddings + RRF
│   ├── server.py            # + 2 neue Tools (gesamt 10)
│   └── domain.py            # unverändert
├── scripts/ingest.py        # NEU: manueller Einstiegspunkt für den Ingest
├── index/                   # NEU: SQLite-DB (maskierte Chunks + Vektoren), gitignored
└── output/
    └── pseudonym_mapping.md # NEU: Auflösung Pseudonym → Klarname, gitignored
```

Kernprinzipien (aus Phase A übernommen):

- **Read-only bleibt read-only:** Dokument-Download ausschließlich über
  `http.get()`. Keine neuen HTTP-Methoden.
- **Eine Stelle entscheidet über PII:** `rag/maskierung.py` ist die einzige
  Stelle, die bestimmt, was vom Dokumenttext LLM-sichtbar wird — analog zu
  `privacy.py` für Mitgliederdaten. Da die Maskierung beim Indexieren
  passiert, enthält der Index nur maskierten Text; nachgelagerte Komponenten
  (Suche, Tools) können konstruktionsbedingt keine Klarnamen leaken.
- **Ingest und Serving getrennt:** Der Ingest läuft als manuelles Skript und
  ist der einzige Teil mit Webling-Zugriff. Der MCP-Server liest zur Laufzeit
  nur den lokalen Index — schnell, offline-fähig.

---

## Ingest-Pipeline (`scripts/ingest.py`)

Vier Schritte, manuell angestoßen, wenn neue Dokumente in Webling liegen:

### 1. Sync

- Alle Jahresordner über die API auflisten, Dokumente herunterladen.
- **Inkrementell:** bereits indexierte Dokumente (Webling-ID + Änderungsdatum
  bzw. Größe) werden übersprungen; in Webling gelöschte Dokumente werden aus
  dem Index entfernt.
- Rohdateien nur temporär (Temp-Verzeichnis), nie dauerhaft gespeichert — auf
  der Platte verbleibt nur der maskierte Index.

### 2. Textextraktion (`rag/extraktion.py`)

- PDF über `pypdf`, Word über `python-docx`.
- Dateitypen ohne Extraktor (Bilder, Excel) und PDFs ohne Textebene
  (Scans) werden übersprungen und in der Ingest-Zusammenfassung als
  „nicht indexiert" ausgewiesen — Phil sieht, was die Suche nicht kennt.

### 3. Maskierung (`rag/maskierung.py`) — zweistufig

- **Stufe 1, deterministisch:** Mitgliederliste frisch aus der Webling-API.
  Pro Mitglied werden Namensvarianten gebildet („Max Mustermann",
  „Mustermann, Max", „M. Mustermann", Nachname allein) und im Text durch das
  Pseudonym `M-<Webling-ID>` ersetzt — **dieselben IDs wie in den
  Phase-A-Tools**, damit Claude Suchtreffer und Mitglieder-Tools verknüpfen
  kann.
- **Stufe 2, Sicherheitsnetz:** NER (spaCy, deutsches Modell, z.B.
  `de_core_news_md`) erkennt Personennamen außerhalb der Mitgliederliste
  (Gäste, Verbandsvertreter, Ex-Mitglieder) → Ersatz durch `P-1`, `P-2`, …
  (pro Dokument stabil).
- **Regex-Pässe** zusätzlich für E-Mail-Adressen, Telefonnummern, IBANs sowie
  volle Geburtsdaten mit Geburts-Kontext („geboren am 15.03.1961", „geb. …") —
  volle Geburtsdaten sind laut Projektregeln verboten; Sitzungs-/Beschlussdaten
  ohne Geburts-Kontext bleiben erhalten.
- **Best-Effort-Charakter (bewusster Trade-off):** Spitznamen, Tippfehler und
  Umschreibungen („unser Kassenwart") werden nicht zuverlässig erkannt.
  Restrisiko von Phil als Vorstand akzeptiert; deutlich kleiner als bei
  ungefiltertem Text.

### 4. Mapping & Chunking

- Auflösung Pseudonym → Klarname nach `output/pseudonym_mapping.md`
  (gitignored, wird bei jedem Ingest überschrieben). Phil schlägt dort lokal
  nach.
- Maskierter Text wird in Chunks von ~400 Tokens mit ~50 Tokens Überlappung
  geschnitten.
  Jeder Chunk trägt Metadaten: Dokumentname, Webling-Dokument-ID, Jahr,
  Position im Dokument.

---

## Suche (`rag/suche.py`)

- **Speicher:** eine SQLite-Datei in `index/` — FTS5-Tabelle für BM25,
  Embedding-Vektoren via `sqlite-vec` in derselben Datei.
- **Embeddings:** `intfloat/multilingual-e5-small` (sentence-transformers,
  ~120 MB, CPU). Läuft vollständig lokal; es wird ohnehin nur maskierter Text
  vektorisiert. **Achtung bei Modellwechsel:** Query- und Index-Embeddings
  müssen vom selben Modell stammen — ein Wechsel erfordert Re-Indexierung
  (Ingest neu laufen lassen).
- **Fusion:** BM25- und Vektor-Ergebnisse werden per Reciprocal Rank Fusion
  (RRF, Standard-k=60) kombiniert. Keine Tuning-Parameter.
- **Laufzeit:** Embedding-Modell wird beim ersten Suchaufruf geladen (Lazy
  Loading, einmalig ~2–5 s pro Serverstart); danach Suchantworten < 1 s.

## MCP-Tools (neu: 2, gesamt: 10)

| Tool | Parameter | Rückgabe |
|---|---|---|
| `suche_dokumente` | `frage` (Freitext), `jahr?` (Filter), `max_treffer?` (Default 5) | Top-Chunks: maskierter Ausschnitt + Dokumentname, Jahr, Score |
| `lies_dokument` | `dokument_id` | Maskierter Volltext eines Dokuments |

Ablauf aus Nutzersicht: Phil fragt in natürlicher Sprache → Claude ruft
`suche_dokumente` auf → formuliert aus den maskierten Chunks eine normale
Antwort **mit Quellenangabe** (Dokumentname, Jahr) und kann Passagen wörtlich
belegen. Pseudonyme löst Phil lokal über `output/pseudonym_mapping.md` auf
oder kombiniert sie direkt mit den Phase-A-Mitglieder-Tools.

## Fehlerbehandlung & Logging

- Tools fangen Exceptions, liefern verständliche deutsche Fehlermeldungen,
  nie Stacktraces ans LLM.
- Fehlender Index → klare Meldung: „Kein Index gefunden — bitte zuerst
  scripts/ingest.py ausführen."
- Ingest bricht bei API-Fehlern sauber ab; übersprungene Dokumente werden am
  Ende als Zusammenfassung gemeldet.
- Logging ohne PII: nur Dokument-IDs, Zähler, Fehlertypen (wie Phase A).

## Testing

- **Kritischster Test — PII-Sweep für den Index:** Fixture-Dokumente mit
  fiktiven Namen, E-Mails, Telefonnummern, IBANs durchlaufen die Maskierung;
  Test prüft, dass keiner der verbotenen Werte im Index oder in
  Tool-Responses auftaucht (Erweiterung des Phase-A-Sweep-Musters).
- Maskierungs-Tests: Namensvarianten, NER-Fallback für Nicht-Mitglieder,
  Pseudonym-Stabilität pro Dokument.
- Such-Tests: Fixture-Index mit bekannten Dokumenten; Hybridsuche findet
  erwartete Chunks; Jahr-Filter greift.
- Ingest-Tests: Inkrementalität (unverändert → übersprungen, gelöscht →
  entfernt) mit gemocktem Client.
- Wie Phase A: nur fiktive Personen, kein Live-API-Zugriff in Tests.
  Manueller Live-Check + E2E-Test als Abschluss.

## Verifikationspunkte (in dieser Reihenfolge, vor allem anderen)

1. **Dokument-Download:** Bestätigen, dass der read-only Key
   Dokument-**Inhalte** via GET liefert (Phase A listet nur Dateinamen).
   Falls nicht → Berechtigungs-/API-Frage klären, bevor irgendetwas gebaut
   wird.
2. **Extraktionsqualität:** 2–3 echte Dokumente (Satzung, ein Protokoll)
   probeweise extrahieren — liefert `pypdf` brauchbaren Text?
3. **NER-Qualität:** spaCy-Modell gegen einen maskierten Probetext prüfen,
   bevor die Stufe-2-Maskierung als Sicherheitsnetz gilt.

## DSGVO-Einordnung

- Tool-Responses enthalten ausschließlich maskierten Text → Stufe 2
  (pseudonymisiert) nach phil-os-Regeln → Claude API zulässig.
- Klardaten (`output/pseudonym_mapping.md`, temporäre Rohdateien beim
  Ingest) verlassen den lokalen Rechner nicht → Stufe 3 bleibt lokal.
- Deshalb bewusst **kein Server-Hosting** in dieser Phase: Auf einem
  gemieteten Server lägen Mapping-Datei und Ingest-Rohdaten außerhalb von
  Phils Kontrolle. Hosting wird ggf. Thema der Klarnamen-Phase.

## Abhängigkeiten (neu)

- `pypdf`, `python-docx` (Extraktion)
- `spacy` + `de_core_news_md` (NER)
- `sentence-transformers` + Modell `intfloat/multilingual-e5-small` (~120 MB)
- `sqlite-vec` (Vektoren in SQLite)

## Code-Stil

Wie Phase A: Deutsch für Kommentare/Docstrings, kein Overengineering,
Logging statt print, Konfiguration über `.env`.
