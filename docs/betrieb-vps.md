# Betrieb auf dem Hetzner-VPS

## Server (Stand 2026-07-29)

| | |
|---|---|
| Typ | Hetzner **CX23** (2 vCPU, 4 GB, 38 GB), Rechenzentrum Nürnberg |
| Hostname / IP | `<HOSTNAME>` / `203.0.113.10` |
| OS | Ubuntu 24.04.4 LTS, Python 3.12.3 |
| Zugang | **nur per SSH-Key**, Passwort-Login abgeschaltet |
| Nutzer | `root` (Administration), `webling` (App, kein Passwort, kein sudo) |

CX22/CPX11/CAX11 gibt es nicht mehr — CX23 ist die aktuelle Einstiegsgröße.
AVV: Bestandteil des Hetzner-Vertrags, https://www.hetzner.com/de/legal/legal-overview

## Voraussetzungen (einmalig, siehe Spec „Offene Punkte“)

1. ~~Server bestellen~~ erledigt (siehe Tabelle oben).
2. (Sub-)Domain `chat.example.org` mit A-Record auf `203.0.113.10`
   — **offen**, Anfrage an den Domain-Verwalter. Blockiert das Caddy-Zertifikat.
3. Anthropic-API-Key mit Budget-Limit (console.anthropic.com -> Billing -> Limits)
   — erledigt.
4. Privates GitHub-Repo — vorhanden. Phase-C-Code liegt auf
   Branch `phase-c-chat`; **vor dem Deploy nach `master` mergen**, sonst zeigt der
   Server auf einen anderen Stand als diese Doku beschreibt.

## Server einrichten

**Erledigt am 2026-07-29:**

- Nutzer `webling` (`adduser --disabled-password --gecos '' webling`), Key aus
  `/root/.ssh/authorized_keys` übernommen
- `fail2ban` und `ufw` installiert; Firewall aktiv mit 22/tcp, 80/tcp, 443/tcp
- Härtung in `/etc/ssh/sshd_config.d/00-haertung.conf`:
  `PasswordAuthentication no`, `KbdInteractiveAuthentication no`,
  `PermitRootLogin prohibit-password`

> **Stolperstein cloud-init:** Wird ein Hetzner-Server *ohne* SSH-Key bestellt,
> legt cloud-init `/etc/ssh/sshd_config.d/50-cloud-init.conf` mit
> `PasswordAuthentication yes` an. SSH nimmt den **zuerst** gelesenen Wert, und
> die Dateien werden alphabetisch eingelesen — eine `99-*.conf` bleibt deshalb
> wirkungslos. Darum heißt die Härtungsdatei `00-*`. Nach jeder Änderung prüfen
> mit `sshd -T | grep -i passwordauthentication` (nicht nur `sshd -t`, das testet
> ausschließlich die Syntax).

**Offen:**

- Caddy installieren (apt-Repo von caddyserver.com), `deploy/Caddyfile` mit
  echter Domain nach `/etc/caddy/Caddyfile`, `systemctl reload caddy`
  — sinnvoll erst, wenn der A-Record steht (sonst schlägt die Zertifikatsausstellung fehl)
- Vor dem `reload`: **Basic-Auth-Hash einsetzen**, sonst startet Caddy nicht
  (`<BCRYPT-HASH>` ist ein Platzhalter). Siehe nächster Abschnitt.

## Zugangsschutz (zwei Schlösser)

`chat.example.org` ist per DNS weltweit auflösbar — der Name ist öffentlich,
die Daten sind es nicht. Zwei unabhängige Schichten:

1. **Basic Auth in Caddy** = geteiltes Vorschloss. Hält Scan-Bots und
   Passwort-Rateversuche von der Loginmaske fern. Ein Passwort für alle.
2. **App-Login** (`auth.py`) = der eigentliche Zugang. Pro Person ein Konto,
   Argon2id, serverseitige Sessions, keine Selbstregistrierung
   (`scripts/nutzer_anlegen.py`), 5 Fehlversuche pro 15 Min und IP.

Ohne gültige Session liefern `/api/status` und `/api/chat` **401**, `/` leitet
auf `/login` um. Öffentlich erreichbar sind nur die Loginmaske und `/static/*`
(Frontend-Gerüst, keine Vereinsdaten). `/docs`, `/redoc` und `/openapi.json`
sind in `app.py` abgeschaltet.

Hash für Schicht 1 erzeugen (auf dem Server, nach der Caddy-Installation):

```
caddy hash-password
```

Passwort zweimal eingeben, die Ausgabe (`$2a$14$…`) in `/etc/caddy/Caddyfile`
anstelle von `<BCRYPT-HASH>` einsetzen, dann `systemctl reload caddy`.
Das `$` **nicht** escapen. Prüfen: `caddy validate --config /etc/caddy/Caddyfile`.

> [!NOTE]
> Das in-memory Rate-Limit zählt **pro IP** und ist nach einem Neustart leer —
> gegen verteilte Versuche schützt es nicht. Die eigentliche Außenhaut sind
> daher **lange Passphrasen** auf den Vorstandskonten.

Die ACME-Challenge (`/.well-known/acme-challenge/`) beantwortet Caddy intern,
bevor Basic Auth greift — die Zertifikatsausstellung wird also nicht blockiert.

## App installieren

Zugang zum privaten Repo läuft über einen **Deploy-Key** (erzeugt 2026-07-29):
`/home/webling/.ssh/github_deploy`, eingebunden über `/home/webling/.ssh/config`
(`Host github.com` -> `IdentityFile ~/.ssh/github_deploy`). Der öffentliche Teil
(`~/.ssh/github_deploy.pub`) muss im GitHub-Repo unter *Settings -> Deploy keys*
mit **Lesezugriff** hinterlegt werden — ohne das schlägt `git clone` fehl.
Neuen Deploy-Key erzeugen: `ssh-keygen -t ed25519 -N '' -f ~/.ssh/github_deploy`.
Verbindung testen: `ssh -T git@github.com` (Erfolg = Begrüßung mit Repo-Namen).

    sudo -iu webling
    git clone git@github.com:<ACCOUNT>/webling-mcp.git webling-mcp
    cd webling-mcp && python3 -m venv venv
    venv/bin/pip install -e .
    venv/bin/python -m spacy download de_core_news_md
    cp .env.example .env && nano .env      # Webling- + Anthropic-Keys eintragen
    chmod 600 .env
    venv/bin/python scripts/ingest.py      # Erst-Ingest (Index + Mapping)
    mkdir -p output daten logs
    chmod 700 output daten
    venv/bin/python scripts/nutzer_anlegen.py phil
    crontab deploy/crontab.txt

Dann als root: `deploy/webling-chat.service` nach `/etc/systemd/system/`,
`systemctl enable --now webling-chat`.

## Update einspielen

    sudo -iu webling && cd webling-mcp
    git pull && venv/bin/pip install -e .
    exit                                   # zurück zu root
    systemctl restart webling-chat

`webling` hat bewusst **kein sudo** (und kein Passwort) — Dienste startet immer
root. Login: `ssh root@203.0.113.10` bzw. `ssh webling@203.0.113.10`.

## Prüfen

- `https://chat.example.org` am Handy: Login, Frage mit Klarnamen, Antwort mit Klarnamen,
  Statuszeile „Index vom …“ = heutiges/gestriges Datum
- „Zum Homescreen hinzufügen“ funktioniert (PWA)
- `journalctl -u webling-chat -f` zeigt keine Klarnamen (nur Zähler/Fehlertypen)

## Datenschutz-Merkzettel

- Klarnamen liegen NUR in `output/` und `daten/` (Rechte 700) und in Webling.
- Keine Hetzner-Backups/Snapshots aktivieren (Klarnamen-Dateien!). Alles außer
  `daten/chat.db` ist aus Webling regenerierbar; die Nutzer-Tabelle einmalig
  manuell sichern (`scp`).
- Handy verloren -> Session widerrufen:
  `sqlite3 daten/chat.db "DELETE FROM sessions;"`
