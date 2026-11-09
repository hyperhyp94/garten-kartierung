#!/usr/bin/env python3
"""Setzt das Passwort eines Nutzers. Das Passwort wird NUR von stdin gelesen.

Aufruf:  printf '%s' 'PASSWORT' | .venv/bin/python scripts/set_password.py sven
Oder interaktiv: .venv/bin/python scripts/set_password.py sven   (fragt verdeckt)
"""
import getpass
import sqlite3
import sys
from pathlib import Path

from werkzeug.security import generate_password_hash

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "garten.db"


def main() -> int:
    if len(sys.argv) != 2:
        print("Aufruf: set_password.py <benutzername>", file=sys.stderr)
        return 2
    user = sys.argv[1].strip().lower()
    if sys.stdin.isatty():
        pw = getpass.getpass("Neues Passwort: ")
        if pw != getpass.getpass("Wiederholen: "):
            print("Passwörter stimmen nicht überein.", file=sys.stderr)
            return 1
    else:
        pw = sys.stdin.readline().rstrip("\n")
    if len(pw) < 8:
        print("Mindestens 8 Zeichen.", file=sys.stderr)
        return 1
    conn = sqlite3.connect(DB)
    cur = conn.execute("UPDATE users SET password_hash=? WHERE username=?",
                       (generate_password_hash(pw), user))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        print(f"Nutzer '{user}' nicht gefunden.", file=sys.stderr)
        return 1
    print(f"Passwort für '{user}' gesetzt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
