"""SQLite-Anbindung und Schema.

Das Schema wächst über nummerierte Schritte. Beim Start werden nur die
Schritte ausgeführt, die in der vorhandenen Datenbank noch fehlen.
"""

import sqlite3
from datetime import date

import click
from flask import Flask, current_app, g
from flask.cli import with_appcontext

SCHRITTE = [
    # 1: Nutzer und Gärten (Stufe 1)
    """
    CREATE TABLE nutzer (
        id            INTEGER PRIMARY KEY,
        benutzername  TEXT NOT NULL UNIQUE,
        anzeigename   TEXT NOT NULL,
        rolle         TEXT NOT NULL CHECK (rolle IN ('besitzer', 'meister')),
        passwort_hash TEXT,
        fehlversuche  INTEGER NOT NULL DEFAULT 0,
        gesperrt_bis  TEXT
    );
    INSERT INTO nutzer (benutzername, anzeigename, rolle) VALUES
        ('sven', 'Sven', 'besitzer'),
        ('johannes', 'Johannes', 'meister');

    CREATE TABLE gaerten (
        id           INTEGER PRIMARY KEY,
        name         TEXT NOT NULL,
        adresse      TEXT NOT NULL DEFAULT '',
        flurstuecke  TEXT NOT NULL DEFAULT '[]',
        grenze       TEXT,
        flaeche_m2   REAL,
        ansicht_lat  REAL,
        ansicht_lon  REAL,
        ansicht_zoom REAL,
        erstellt_von INTEGER REFERENCES nutzer (id),
        erstellt_am  TEXT NOT NULL DEFAULT (datetime('now')),
        geaendert_am TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """,
]


def verbinden(pfad) -> sqlite3.Connection:
    con = sqlite3.connect(pfad)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


def hole_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = verbinden(current_app.config["DATENBANK"])
    return g.db


def _schliessen(_fehler=None):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def aktualisieren(pfad) -> None:
    con = verbinden(pfad)
    try:
        stand = con.execute("PRAGMA user_version").fetchone()[0]
        for nummer, sql in enumerate(SCHRITTE, start=1):
            if nummer > stand:
                con.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {nummer};\nCOMMIT;")
    finally:
        con.close()


SICHERUNGEN_BEHALTEN = 14


@click.command("sicherung")
@with_appcontext
def sicherung():
    """Legt eine Kopie der Datenbank in den Ordner „sicherung“ und behält die letzten 14."""
    ordner = current_app.config["DATEN"] / "sicherung"
    ordner.mkdir(exist_ok=True)
    ziel = ordner / f"garten-{date.today().isoformat()}.db"
    quelle = sqlite3.connect(current_app.config["DATENBANK"])
    kopie = sqlite3.connect(ziel)
    try:
        # Die Sicherung von SQLite liefert auch dann einen sauberen Stand, wenn gerade jemand speichert.
        quelle.backup(kopie)
    finally:
        kopie.close()
        quelle.close()
    for alt in sorted(ordner.glob("garten-*.db"))[:-SICHERUNGEN_BEHALTEN]:
        alt.unlink()
    click.echo(f"Gesichert nach {ziel}")


def einrichten(app: Flask) -> None:
    aktualisieren(app.config["DATENBANK"])
    app.teardown_appcontext(_schliessen)
    app.cli.add_command(sicherung)
