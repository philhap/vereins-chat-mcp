# Status freischalten & Mitgliedsbeitrag ableiten — Design

**Datum:** 2026-07-22
**Status:** Von Phil freigegeben (Brainstorming-Session)
**Voraussetzung:** Phase A/B/C fertig auf `phase-c-chat`. Das Webling-Feld `Status`
ist gepflegt (Phil, 2026-07-22).

## Ziel

Das Webling-Feld `Status` (Mitgliedskategorie: A-/P-/B-/C-/D-/E-/F-/CA-Mitglied,
Ehrenmitglied) dem LLM sichtbar machen — analog zum bereits freigegebenen Feld
`Beitritt`. Zusätzlich den **Jahresbeitrag** je Mitglied bereitstellen, aber
**deterministisch aus dem Status abgeleitet** statt aus dem unzuverlässigen
Webling-Feld `Mitgliedsbeitrag` gelesen. Datenschutz-Stufe 2 bleibt unverändert:
An die API gehen nur pseudonyme, niedrig-kardinale Kategorien und Beträge.

## Entscheidung & verworfene Alternativen

Gewählt: **Beitrag aus Status ableiten** (eine feste Beitragsordnung Status→€),
das Webling-Feld `Mitgliedsbeitrag` wird nicht gelesen.

Verworfen:

- **Webling-Feld `Mitgliedsbeitrag` direkt lesen:** Ein read-only-Check an echten
  Daten (2026-07-22) zeigte das Feld als unzuverlässig — mehrere Leerwerte plus mehrere
  Beträge, die nicht zum Status passen (z. B. bei
  C-Mitgliedern). Der Status dagegen ist nahezu vollständig (fast alle Mitglieder) und kategorisch
  eindeutig. Zwei Wahrheiten, die auseinanderlaufen — verworfen.
- **Beitrag vom LLM aus der Legende rechnen lassen:** Bei Geld ist eine plausible
  Falschauskunft teuer; LLM-Arithmetik ist nicht deterministisch/testbar. Der
  Betrag wird serverseitig berechnet und als fertiges Feld geliefert.
- **Nur Status ohne Beitrag (diese Session):** ursprünglich erwogen, dann
  zusammengeführt — die Beitragsordnung liegt vor, das Ableiten ist klein und
  deterministisch, und der abgeleitete Betrag macht Status-Fehler sichtbar
  (siehe Konsistenz-Check).

Bewusst akzeptiert:

- **Der abgeleitete Beitrag ist nur so korrekt wie der Status.** Ein falscher
  Status → falscher Beitrag. Das ist gewollt sichtbar: ein 12-Jähriger als
  C-Mitglied würde 300 € zeigen, was offensichtlich falsch ist und zur Korrektur
  in Webling führt. Der Alters-/Kategorie-Check unten deckt genau solche Fälle auf.
- **`Ehrenmitglied` ist sehr klein besetzt.** Eine so seltene Kategorie
  ist zusammen mit anderen Quasi-Identifikatoren theoretisch identifizierend. Da
  die API nur Pseudonyme sieht und Ehrenmitgliedschaft im Verein ohnehin bekannt
  ist, gleiches akzeptiertes Restrisiko wie einzelne Vornamen in Phase B.

## Beitragsordnung — eine Quelle der Wahrheit

Eine benannte Konstante (`domain.py`), aus der **beide** Ausgaben stammen — der
abgeleitete Betrag *und* die Legende. So können sie nicht auseinanderlaufen. Der
Schlüssel ist der exakte Webling-Wert (inkl. Klammerzusatz bei CA):

```python
BEITRAGSORDNUNG = {
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
```

Phil ändert Bedeutung oder Betrag hier an einer Stelle. Quelle laut Phil: die
aktuelle Beitrittserklärung (liegt im RAG-Index).

## Architektur & Komponenten

Kleiner, additiver Eingriff entlang des bestehenden Feld-Freigabe-Musters
(`members.py` → `privacy.py` → `datenqualitaet`), plus die abgeleitete
Beitragslogik und der Konsistenz-Check in `domain.py`.

**1. Feld laden — `client/members.py`**
- `FELD_STATUS = "Status"`
- In `_normalisiere`: `"status": props.get(FELD_STATUS) or ""`
- Das Webling-Feld `Mitgliedsbeitrag` wird **nicht** geladen.

**2. Ableiten & Konstante — `domain.py`**
- `BEITRAGSORDNUNG` wie oben.
- `def mitgliedsbeitrag(mitglied) -> int | None`: Nachschlag über `status`.
  Leerer oder unbekannter Status → `None` (nicht raten). Unbekannte Werte werden
  geloggt (nur der Wert, kein PII).
- `def status_kategorie(mitglied) -> str | None`: Rückgabe des Status oder `None`
  (Adapter für `datenabdeckung`, das eine Feldfunktion erwartet).
- `def status_legende() -> str`: erzeugt den Legendentext aus `BEITRAGSORDNUNG`
  (Bedeutung + Betrag je Code), für den System-Prompt.

**3. Freigeben — `privacy.py`**
- In `pseudonymisiere`: `"status": mitglied.get("status", "")` und
  `"mitgliedsbeitrag": domain.mitgliedsbeitrag(mitglied)`.
- Damit liefern `list_members` und `get_member` beide Felder automatisch.

**4. Datenqualität — `tools.py`**
- In `baue_list_members` unter `datenqualitaet` zusätzlich
  `"status": domain.datenabdeckung(gefiltert, domain.status_kategorie)`.
- Der System-Prompt weist bereits an, gemeldete Lücken zu benennen — ein
  Mitglied ohne Status heißt „in Webling nicht eingetragen", nicht „0 €".

**5. Legende & Begriffsklärung — `webling_chat/chat.py`**
- `SYSTEM_PROMPT` bekommt die aus `BEITRAGSORDNUNG` erzeugte Legende plus einen
  Satz, der drei ähnlich klingende Felder trennt:
  - `status` = Mitgliedskategorie (A/P/…),
  - `mitgliedsbeitrag` = Jahresbeitrag in € (aus `status` abgeleitet),
  - `beitragsstatus` = bis zu welchem **Jahr** bezahlt (unverändert).
- Der MCP-Pfad (`server.py`, Claude Code) braucht die Legende nicht zwingend;
  die Feldbedeutungen sind für einen Entwickler aus dem Code ersichtlich. Kein
  Eingriff in `server.py`.

**6. Alters-/Kategorie-Konsistenz-Check — `domain.py` + `scripts/status_check.py`**
- `def status_widersprueche(mitglieder, jahr) -> list[dict]`: prüft je Mitglied
  das maßgebliche Alter gegen die Kategorie und liefert die Ausreißer
  (pseudonymfähig: id, status, alter, grund).
- **Maßgebliches Alter = `jahr − geburtsjahr − 1`.** Wer im laufenden Jahr X wird,
  zählt noch als „unter X". Bewusst anders als die Jubiläumslogik
  (`wird 65 im Jahr` = `jahr − geburtsjahr`, ohne −1) — beide bleiben getrennt,
  keine Vereinheitlichung.
- Altersregeln (nur klare Widersprüche, konservativ, keine Fehlalarme an Grenzen):
  - `F-Mitglied` (Kinder bis 12): Widerspruch, wenn Alter > 12
  - `E-Mitglied` (13–18): Widerspruch, wenn Alter < 13 oder > 18
  - `A/B/C/D-Mitglied` (erwachsen): Widerspruch, wenn Alter < 18
  - `P/CA/Ehrenmitglied`: keine Altersregel
  - Mitglieder ohne Geburtstag werden übersprungen (kein Alter, kein Urteil).
- `scripts/status_check.py`: dünner read-only-Wrapper (wie `live_check.py`).
  Druckt nur Pseudonyme (`M-<id>`) + Alter + Grund auf die Konsole; echte Namen
  ausschließlich in eine lokale Datei unter `output/` (gitignored). Neuer
  Dateiname `status_pruefung.md` wird in `privacy.ERLAUBTE_DATEINAMEN` ergänzt,
  damit das Schreiben über `privacy.schreibe_namensliste()` läuft (kein Bypass
  der Whitelist).

## Privacy

Unverändert Stufe 2. `status` (9 Kategorien) und `mitgliedsbeitrag` (feste
Beträge) sind weder Name, Vorname, E-Mail, Adresse, Telefon noch Datum — der
PII-Sweep-Test bleibt grün. Der Konsistenz-Check schreibt Namen nur lokal über
den bestehenden `schreibe_namensliste()`-Pfad.

## Fehlerbehandlung

- Leerer/unbekannter Status → `mitgliedsbeitrag = None`, als Datenlücke gemeldet,
  nie als 0 € geraten.
- Mitglied ohne Geburtstag → aus dem Konsistenz-Check ausgenommen.
- Webling-Fehler → wie gehabt als Tool-Ergebnis ans Modell (`_sicher`).

## Tests

Knüpft an die 168 bestehenden Tests an (pytest):

1. **Ableitung `mitgliedsbeitrag`:** je Kategorie der korrekte Betrag; leerer und
   unbekannter Status → `None`. Tabellen-getrieben aus `BEITRAGSORDNUNG`.
2. **Legende-Konsistenz:** `status_legende()` enthält jeden Code aus
   `BEITRAGSORDNUNG` mit passendem Betrag (eine Quelle, kein Drift).
3. **Whitelist:** `pseudonymisiere` liefert `status` und `mitgliedsbeitrag`;
   PII-Sweep über `list_members`/`get_member` weiterhin grün.
4. **Datenqualität:** `datenqualitaet.status` meldet gepflegt/gesamt korrekt,
   auch mit einem Mitglied ohne Status.
5. **Konsistenz-Check:** F/E/A-D/Grenzfälle inkl. der −1-Regel (wer dieses Jahr
   18 wird → zählt als 17 → bei A/B/C/D ein Widerspruch); Mitglied ohne
   Geburtstag wird übersprungen. Fiktive Personen, kein Live-Zugriff.
6. **E2E manuell (Phil):** im Chat „welche Kategorie/​welcher Beitrag hat M-…",
   „wer ist Aktivmitglied", „zeig mir Status-Ausreißer".

## Offene Punkte / bewusst nicht

- **Status-Datenqualität** bleibt Phils Aufgabe in Webling; der Check zeigt die
  altersbasierten Ausreißer, kann aber z. B. ein falsches A statt P nicht sehen.
- **Konsistenz-Check als Chat-Tool** (statt nur Skript) ist später ohne Umbau
  ergänzbar (`status_widersprueche` ist bereits pseudonymfähige Domain-Logik),
  in dieser Session bewusst nicht.
