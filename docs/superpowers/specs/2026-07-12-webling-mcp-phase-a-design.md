# webling-mcp — Phase A Design

**Datum:** 2026-07-12
**Status:** Entwurf validiert (Brainstorming-Session mit Phil)
**Projekt:** Vereins-Bot Phase 3 / eigenständiges Package `webling-mcp`

---

## Kontext & Ziel

Ein Sportverein verwaltet seine knapp 100 Mitglieder in Webling. Phase 1+2 des
Vereins-Bots (Telegram, ohne LLM) sind abgeschlossen. Phase 3 baut einen
**MCP-Server**, der Webling-Daten für Claude Code / Claude Desktop nutzbar
macht — primär für den Vorstandsalltag ("Wer hat noch nicht bezahlt?",
"Wer hat dieses Jahr ein Jubiläum?"), sekundär als Referenzarchitektur
für DSGVO-konforme LLM-Integrationen (späterer GitHub-Showcase).

**Primärer Konsument:** Phil selbst über Claude Code / Claude Desktop.

## Entscheidungen (aus Brainstorming 2026-07-12)

| Thema | Entscheidung |
|---|---|
| Nutzungskontext | Eigennutzung zuerst, Showcase folgt daraus |
| PII-Behandlung | Pseudonymisierung im MCP-Layer + lokales Rendern |
| Repo-Struktur | Eigenständiges Repo/Package `Projekte/webling-mcp/` |
| API-Zugang | Neuer Webling-API-Key mit nur Lese-Rechten |
| Tool-Scope | 4 generische + 4 Domain-Tools |
| Framework | FastMCP (Python, stdio) — Entscheidung vom 2026-04-23 |
| Policy-Layer (Rollen, Audit-Log) | NICHT in Phase A — kommt in Phase C |

## Nicht-Ziele (Phase A)

- Keine Schreiboperationen auf Webling (weder Code noch Berechtigung)
- Kein RAG-Layer (Phase B), kein Policy-/Auth-Layer (Phase C)
- Keine baden.liga.nu-Integration
- Keine Migration des Telegram-Bots auf dieses Package (optional, später)

---

## Architektur

Drei Schichten, jede ohne Kenntnis der darüberliegenden:

```
webling-mcp/
├── CLAUDE.md               # Projektregeln (DSGVO-Design, Stil)
├── README.md               # Showcase-tauglich: Architektur, Setup, Demo
├── pyproject.toml          # Package "webling_mcp", installierbar
├── .env.example            # WEBLING_BASE_URL, WEBLING_MCP_API_KEY
├── .gitignore              # .env, output/, __pycache__
├── src/webling_mcp/
│   ├── server.py           # FastMCP-Server, registriert die 8 Tools
│   ├── client/             # Schicht 1: purer Webling-API-Client
│   │   ├── http.py         #   nur GET — Schreiboperationen existieren nicht
│   │   ├── members.py      #   Mitglieder inkl. Bulk-Abruf
│   │   └── documents.py    #   Jahresordner + Dokumentlisten
│   ├── privacy.py          # Schicht 2: Pseudonymisierung + lokales Rendern
│   └── domain.py           # Auswertungslogik (Port aus webling_members.py)
├── output/                 # lokal gerenderte Namenslisten (gitignored)
└── tests/
```

- **`client/`** kennt weder MCP noch LLM. Wiederverwendbar (später auch vom
  Telegram-Bot als Dependency nutzbar). `http.py` implementiert ausschließlich
  GET — Schreibschutz doppelt: im Code und per read-only API-Key.
- **`privacy.py`** ist die einzige Stelle, an der entschieden wird, welche
  Felder das LLM sieht.
- **`domain.py`** portiert die bewährte Filterlogik aus
  `vereins-bot-mvp/webling_members.py` (Beiträge, Jubiläen, Mannschaften,
  Statistik) und arbeitet auf unpseudonymisierten Daten — die
  Pseudonymisierung passiert erst an der Tool-Grenze in `server.py`.

### Performance

Mitglieder werden per **Bulk-Abruf** geladen
(`GET /member/id1,id2,id3,...` mit kommaseparierten IDs) statt der bisherigen
94 Einzel-Calls des Bots. **Verifikationspunkt Nr. 1 der Implementierung:**
Bulk-Abruf gegen die echte API testen. Fallback, falls nicht unterstützt:
`/replicate`-Endpoint; letzter Fallback: Einzel-Calls wie bisher.

---

## Privacy-Design (Kern des Projekts)

### Whitelist statt Blacklist

`privacy.py` lässt pro Mitglied **nur explizit freigegebene Felder** in
Tool-Responses durch:

| Feld an Claude | Quelle / Regel |
|---|---|
| `id` = `M-<Webling-ID>` | stabile Webling-Mitglieds-ID; keine lokale Mapping-Tabelle nötig |
| `geburtsjahr` | nur das Jahr — volles Geburtsdatum bleibt lokal |
| `geschlecht` | direkt (`w`/`m`) |
| `mannschaft` | direkt (enum) |
| `rang` | direkt (int) |
| `beitragsstatus` | direkt (enum, Jahreszahl) |

Name, Vorname, E-Mail, Adresse, Telefon, volles Geburtsdatum: **niemals** in
einer Tool-Response. Neue Webling-Felder sind durch den Whitelist-Ansatz
automatisch blockiert, bis sie bewusst freigeschaltet werden.

Abgeleitete Felder sind zulässig, sofern sie kein gesperrtes Feld
rekonstruieren: `jubilaeen` gibt z.B. Alter und Geburts**monat** zurück
(für die Planung nötig), aber nie den Geburtstag.

DSGVO-Einordnung: Tool-Responses sind pseudonymisiert (Stufe 2 nach
phil-os-Regeln) → Claude API zulässig. Klardaten (Stufe 3) verlassen den
lokalen Rechner nicht.

### Lokales Rendern

Domain-Tools geben an Claude nur Aggregate + Pseudonyme zurück und schreiben
parallel eine aufgelöste Markdown-Liste **mit echten Namen** nach `output/`.
Die Tool-Response enthält den Dateipfad; Phil öffnet die Datei lokal.

- Pro Tool ein fester Dateiname (`output/beitraege.md`,
  `output/jubilaeen.md`, `output/mannschaften.md`) — wird bei jedem Aufruf
  überschrieben, keine Ansammlung alter PII-Dateien.
- `output/` steht in `.gitignore`.

---

## Tools (8)

### Generisch — Rohdaten, pseudonymisiert

| Tool | Parameter | Rückgabe |
|---|---|---|
| `list_members` | `mannschaft?`, `geburtsjahr_von?`, `geburtsjahr_bis?` | Liste pseudonymisierter Mitglieder |
| `get_member` | `id` (z.B. `M-1234`) | Ein Mitglied, Whitelist-Felder |
| `list_groups` | — | Mannschaften/Gruppen mit Mitgliederzahl |
| `list_documents` | `jahr?` (Default: aktuelles Jahr) | Dateinamen im Jahresordner (Dateinamen gelten als unkritisch) |

### Domain — fertige Auswertungen, jeweils + lokale Namensdatei

| Tool | Parameter | Rückgabe an Claude | Lokale Datei |
|---|---|---|---|
| `unbezahlte_beitraege` | `jahr?` (Default: aktuelles Jahr) | Anzahl + Pseudonym-Liste | `output/beitraege.md` |
| `jubilaeen` | `jahr?` | Jubilare (Pseudonym, Alter, Monat) | `output/jubilaeen.md` |
| `mannschaften` | — | Aufstellungen (Pseudonym, Rang) | `output/mannschaften.md` |
| `mitglieder_statistik` | — | Statistik nach Geburtsjahr/Geschlecht (reines Aggregat) | keine |

Jubiläums-Regel (aus Phase 2 übernommen): Mitglieder, die im Zieljahr 65, 70,
75, 80, … werden.

---

## Fehlerbehandlung & Logging

- Jedes Tool fängt Exceptions und gibt eine verständliche deutsche
  Fehlermeldung als Tool-Result zurück (kein Stacktrace ans LLM).
- Logging nur Zähler und Fehlertypen, **nie PII** (wie im Bot).
- Fehlende/falsche `.env`-Konfiguration wird beim Serverstart klar gemeldet
  (nicht erst beim ersten Tool-Call).

## Testing

- Unit-Tests mit Fixture-Daten (fiktive Mitglieder), **kein Live-API-Zugriff
  in Tests**.
- Kritischster Test: `privacy.py`-Whitelist — stellt sicher, dass Name,
  E-Mail und volles Geburtsdatum in keiner Tool-Response auftauchen können
  (Test iteriert über alle Tool-Response-Builder mit voll befüllten
  Fixture-Mitgliedern und prüft auf verbotene Felder/Werte).
- Domain-Logik-Tests portiert aus `vereins-bot-mvp/tests/`.
- Manueller End-to-End-Test gegen die echte API als letzter
  Implementierungsschritt (read-only, unkritisch).

## Anbindung & Voraussetzungen

- Registrierung als stdio-Server in Claude Code (`.mcp.json` im
  phil-os-Root oder projekt-lokal) und optional Claude Desktop
  (`claude_desktop_config.json`).
- **Vorbereitung durch Phil (einmalig, ~5 Min):** in der Webling-Admin-UI
  einen neuen API-Key mit nur Lese-Rechten anlegen → `.env` als
  `WEBLING_MCP_API_KEY`.
- `.env` enthält: `WEBLING_BASE_URL` (https://verein.webling.eu/api/1),
  `WEBLING_MCP_API_KEY`.

## Code-Stil

- Deutsch für Kommentare und Docstrings (wie im Bot-Projekt)
- Kein Overengineering — einfach und funktional
- Logging statt print, Konfiguration über `.env` / `os.environ.get()`
