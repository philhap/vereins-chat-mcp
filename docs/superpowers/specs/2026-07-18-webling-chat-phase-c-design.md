# Phase C: Chat-PWA mit Auth & Klarnamen-Rücksubstitution — Design

**Datum:** 2026-07-18
**Status:** Von Phil freigegeben (Brainstorming-Session)
**Voraussetzung:** Phase A (MCP-Server, 8 Tools) und Phase B (RAG-Hybridsuche, 10 Tools) fertig auf master.

## Ziel

Smartphone-Zugriff auf die Vereinsdaten eines Sportvereins über eine eigene Chat-Web-App (PWA)
auf einem EU-VPS — mit Login und mit **Klarnamen in den Antworten**, ohne die
Datenschutz-Stufe 2 zu verlassen: Die Anthropic-API sieht weiterhin ausschließlich
Pseudonyme; die Übersetzung in beide Richtungen passiert auf dem eigenen Server.

## Entscheidung & verworfene Alternativen

Gewählt: **Variante B — FastAPI-Monolith auf Hetzner-VPS, Ingest läuft ebenfalls auf dem VPS.**

Verworfen:

- **(a) Remote-MCP + Custom Connector in der Claude-App:** beste Chat-UX ohne eigenes
  Frontend, aber Klarnamen in Antworten sind prinzipiell unmöglich — die Tool-Antwort geht
  direkt ans LLM, es gibt keine Stelle zwischen LLM und Anzeige für eine Rücksubstitution.
  Klarnamen waren Phil wichtig → raus. Später als Zusatz-Endpoint ergänzbar (Variante C),
  nichts im Design verbaut das.
- **(c) Alles lokal + Tailscale:** 0 €, DSGVO-maximal, aber gleiches Klarnamen-Problem
  (Client wäre die Claude-App) plus Abhängigkeit vom laufenden Heim-PC.
- **Variante A (wie B, aber Ingest bleibt auf dem Heim-PC + Sync):** verworfen, weil der
  Heim-PC dann Single Point of Failure für die Index-Aktualität bleibt. Da das
  Klarnamen-Mapping ohnehin auf dem VPS liegt (AVV), spricht nichts gegen den Ingest dort.

Bewusst akzeptiert:

- **Anthropic-API-Key nötig** — die PWA zahlt pro Nutzung (nicht übers Claude-Abo);
  bei Vereinsvolumen wenige Euro/Monat.
- **Klarnamen-Dateien liegen auf dem VPS** (Hetzner, Deutschland, AVV ist Vertragsbestandteil,
  abrufbar unter <https://www.hetzner.com/de/legal/legal-overview>) — Auftragsverarbeitung
  statt „nie aus dem Haus". Abgesichert über Dateirechte, Härtung, keine Offsite-Backups.

## Architektur & Komponenten

Ein Hetzner-VPS (CX22, 4 GB RAM, Nürnberg/Falkenstein, Ubuntu LTS) betreibt eine
FastAPI-App mit drei Aufgaben: PWA ausliefern, Chat via Anthropic-API mit Tool-Use
beantworten, täglicher Ingest per Cron. Alles im selben Repo:

```
src/
├── webling_mcp/          # bestehend, bleibt für Claude Code (stdio) nutzbar
│   ├── tools.py          # NEU: Tool-Logik aus server.py herausgezogen
│   ├── server.py         # registriert tools.py nur noch für FastMCP
│   └── privacy.py, client/, rag/   # unverändert
└── webling_chat/         # NEU
    ├── app.py            # FastAPI: Routen, Session-Middleware, Statuszeile
    ├── auth.py           # Login, Argon2id, Nutzer- & Session-Tabellen (SQLite)
    ├── policy.py         # erlaubte_tools(rolle) — einzige Policy-Stelle
    ├── chat.py           # Tool-Use-Schleife gegen die Anthropic-API
    ├── vormaskierung.py  # Klarname → Pseudonym (Nutzereingabe)
    ├── ruecksubstitution.py  # Pseudonym → Klarname (nur Richtung Browser)
    └── static/           # Chat-UI: eine HTML-Seite, Vanilla JS, manifest.json
```

Kernentscheidungen:

1. **Ein gezielter Refactor, sonst keine Änderung an Phase A/B:** Tool-Funktionen wandern
   aus den FastMCP-Dekoratoren in ein neutrales `tools.py`; Consumer sind der stdio-Server
   (wie bisher) und die Chat-Schleife. Kein MCP über HTTP.
2. **Frontend minimal:** eine HTML-Seite, Vanilla JS mit gestreamter Antwort,
   `manifest.json` für „Zum Homescreen hinzufügen". Kein Framework, kein Build-Schritt.
3. **Keine Chat-Historie in v1** (YAGNI): keine Persistenz. Der Verlauf existiert nur für
   die laufende Chat-Session — Anzeige im Browser, pseudonymisierter Verlauf im
   Serverspeicher (siehe Datenfluss). Persistente Historie = eigene PII-Speicherfrage,
   bewusst vertagt.
4. **Modell:** Claude Sonnet (aktuelle Version bei Implementierung) über die Anthropic-API;
   API-Key als Env-Variable auf dem VPS.

## Datenfluss einer Chat-Runde

```
Smartphone ──HTTPS──▶ VPS                        ──▶ Anthropic API
 „Hat Timo Meier       1. Vormaskierung:              sieht nur:
  bezahlt?“               Klarname → M-123            „Hat M-123 bezahlt?“
                       2. Tool-Use-Schleife           Tool-Antworten sind
                          (tools.py)                  bereits pseudonym
 „Timo Meier hat   ◀── 3. Rücksubstitution:      ◀── „M-123 hat noch
  noch nicht bezahlt“     M-123 → Klarname            nicht bezahlt“
```

1. **Vormaskierung:** Der Server ersetzt bekannte Klarnamen in der Nutzerfrage durch
   Pseudonyme — gleiche Logik wie `rag/maskierung.py` (case-insensitive, `\s+`-tolerant).
   Quellen: die knapp 100 Mitgliedsnamen aus Webling plus das NER-Mapping aus dem Ingest.
   Unbekannte Namen bleiben stehen — gleiches akzeptiertes Restrisiko wie Phase B,
   wird im Modul-Docstring dokumentiert.
2. **Verlauf serverseitig:** Der pseudonymisierte Gesprächsverlauf liegt pro Chat-Session
   im Serverspeicher; der Browser schickt nur die neue Nachricht. Es existiert damit kein
   Pfad, über den ein Klarname aus dem Verlauf Richtung API wandern könnte.
   Serverneustart = Verlauf weg (für v1 okay).
3. **Rücksubstitution nur am Ausgang zum Browser:** `M-<id>` → Name via Webling-Stammdaten,
   NER-Pseudonyme via Mapping-Datei; beides auf dem VPS vorhanden (Ingest läuft dort).
   Unbekannte Pseudonyme bleiben unverändert stehen.

**Klarnamen-Grenze:** Anthropic sieht nur Pseudonyme. Der VPS übersetzt (AVV-gedeckt).
Klarnamen existieren nur zwischen VPS und Browser (TLS) und in Dateien auf dem VPS.

## Auth & Policy

- **Nutzer-Tabelle (SQLite):** `id, benutzername, passwort_hash (Argon2id), rolle, aktiv,
  erstellt_am`. Kein Selbst-Registrieren; Anlage per `scripts/nutzer_anlegen.py` auf dem VPS.
- **Sessions serverseitig:** Zufallstoken in `sessions`-Tabelle, Cookie (httponly, secure,
  SameSite=Lax) trägt nur das Token. Laufzeit 30 Tage gleitend. Einzelne Sessions gezielt
  widerrufbar (Handy verloren → Zeile löschen).
- **Brute-Force-Schutz:** Rate-Limit auf `/login`: 5 Fehlversuche pro 15 Minuten pro IP
  (in-memory). Zusammen mit HTTPS und starkem Passwort ausreichend für v1;
  Passkeys sind ein mögliches späteres Upgrade.
- **Policy-Modul `policy.py`:** genau eine Funktion `erlaubte_tools(rolle) -> Liste`,
  heute trivial (Rolle `vorstand` sieht alle 10 Tools), aber die **einzige Stelle**, an der
  die Chat-Schleife ihre Tool-Liste bezieht — gleiche Philosophie wie `privacy.py`.
  Spätere Rollen (z. B. Jugendwart) sind eine Datenänderung, kein Umbau.

Nicht in Phase C (bewusst): rollenabhängige Rücksubstitution, Einladungs-Flows, 2FA,
persistente Chat-Historie. Nichts davon wird durch das Design verbaut.

## Deployment & Betrieb

- **HTTPS:** Caddy als Reverse Proxy mit automatischem Let's Encrypt. Braucht eine
  (Sub-)Domain — offener Punkt, siehe unten.
- **Prozesse:** App als systemd-Service (uvicorn + venv, kein Docker). Ingest als Cron
  täglich 06:00 mit den bestehenden Skripten; Log wie gehabt nur Zähler/Dateinamen.
- **Härtung:** ufw (nur 80/443 + SSH), SSH nur mit Key, fail2ban. `output/` und `.env`
  mit restriktiven Dateirechten (700/600).
- **Backups:** keine nötig — Index und Mapping sind jederzeit per Ingest aus Webling
  regenerierbar; nur die winzige Nutzer-Tabelle einmalig manuell sichern.
  Keine Hetzner-Snapshots/Offsite-Backups mit Klarnamen-Dateien.
- **Code-Transport:** privates GitHub-Repo, Deployment = `git pull`
  auf dem Server. `.gitignore` schützt `.env`, `output/`, Logs bereits.
- **Secrets** (`.env` auf dem VPS): `ANTHROPIC_API_KEY`, `WEBLING_APIKEY` (read-only,
  wie bisher), `SECRET_KEY`.

## Fehlerbehandlung

- Webling nicht erreichbar → Tool-Fehler wird als Tool-Ergebnis ans Modell gereicht,
  das eine verständliche Meldung formuliert (Muster wie Phase A/B).
- Anthropic-Fehler (Überlast, Rate-Limit) → freundliche Chat-Meldung statt Stacktrace.
- Unbekanntes Pseudonym bei Rücksubstitution → bleibt stehen, kein Fehler.
- UI-Statuszeile „Index vom TT.MM." — hängt der Cron-Ingest, fällt es sofort auf.

## Tests

Knüpft an die 106 bestehenden Tests an (pytest):

1. **Auth:** richtiges/falsches Passwort, abgelaufene Session, Rate-Limit,
   Zugriff ohne Login → Redirect.
2. **Vormaskierung & Rücksubstitution:** Unit-Tests inkl. Groß-/Kleinschreibung,
   Zeilenumbrüche, unbekannte Namen/Pseudonyme.
3. **PII-Sweep API-Richtung (Kernstück):** Anthropic-Client gemockt, kompletter
   Chat-Durchlauf mit Klarnamen in der Frage; Assertion über jeden Request-Payload:
   kein bekannter Klarname darin. Gegenstück zum PII-Sweep aus Phase A.
4. **Chat-Schleife:** mit gemocktem Client über mehrere Tool-Use-Runden.
5. **E2E manuell (Phil):** am Handy einloggen, Frage mit Klarnamen stellen,
   Antwort mit Klarnamen erhalten; PII-Stichprobe weiterhin per Skript.

## Offene Punkte (vor bzw. während der Implementierung zu klären)

1. **Domain:** vorhandene (Sub-)Domain nutzen oder günstige (~5 €/Jahr) registrieren.
2. **Anthropic-API-Key:** anlegen und Budget-Limit in der Anthropic-Konsole setzen.
3. **GitHub-Repo:** privates Repo anlegen und master pushen (Transportweg fürs Deployment).
