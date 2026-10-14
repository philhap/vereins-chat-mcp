"""Legt einen Chat-Nutzer an (auf dem VPS ausführen). Passwort via getpass."""

import argparse
import getpass
import sys

from webling_chat import auth


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat-Nutzer anlegen")
    parser.add_argument("benutzername")
    parser.add_argument("--rolle", default="vorstand")
    args = parser.parse_args()

    pw1 = getpass.getpass("Passwort: ")
    pw2 = getpass.getpass("Passwort (Wiederholung): ")
    if pw1 != pw2:
        sys.exit("Passwörter stimmen nicht überein.")
    if len(pw1) < 12:
        sys.exit("Passwort zu kurz (mindestens 12 Zeichen).")

    con = auth.oeffne_db()
    try:
        nutzer_id = auth.lege_nutzer_an(con, args.benutzername, pw1, args.rolle)
    except ValueError as e:
        sys.exit(str(e))
    print(f"Nutzer {args.benutzername!r} angelegt (id={nutzer_id}, rolle={args.rolle}).")


if __name__ == "__main__":
    main()
