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
    # 2: Bestand, Einträge, Medien, Aufgaben, Anleitungen (Stufen 2 bis 5)
    """
    ALTER TABLE gaerten ADD COLUMN eigene_flaeche TEXT;
    ALTER TABLE gaerten ADD COLUMN eigene_m2 REAL;
    ALTER TABLE gaerten ADD COLUMN eigener_umfang REAL;
    ALTER TABLE gaerten ADD COLUMN kalender_token TEXT;

    CREATE TABLE bestand (
        id             INTEGER PRIMARY KEY,
        garten_id      INTEGER NOT NULL REFERENCES gaerten (id) ON DELETE CASCADE,
        art            TEXT NOT NULL CHECK (art IN ('pflanze', 'objekt')),
        kategorie      TEXT NOT NULL,
        name           TEXT NOT NULL,
        lexikon_id     TEXT,
        form           TEXT NOT NULL CHECK (form IN ('punkt', 'linie', 'flaeche')),
        geometrie      TEXT NOT NULL,
        lat            REAL NOT NULL,
        lon            REAL NOT NULL,
        mass           REAL,
        zustand        INTEGER CHECK (zustand BETWEEN 1 AND 5),
        standort_notiz TEXT NOT NULL DEFAULT '',
        archiviert     INTEGER NOT NULL DEFAULT 0,
        erstellt_von   INTEGER REFERENCES nutzer (id),
        erstellt_am    TEXT NOT NULL DEFAULT (datetime('now')),
        geaendert_am   TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX bestand_garten ON bestand (garten_id, archiviert);

    CREATE TABLE anleitungen (
        id               INTEGER PRIMARY KEY,
        schluessel       TEXT UNIQUE,
        titel            TEXT NOT NULL,
        schritte         TEXT NOT NULL DEFAULT '',
        werkzeug         TEXT NOT NULL DEFAULT '',
        sicherheit       TEXT NOT NULL DEFAULT '',
        monat_von        INTEGER CHECK (monat_von BETWEEN 1 AND 12),
        monat_bis        INTEGER CHECK (monat_bis BETWEEN 1 AND 12),
        intervall_monate INTEGER,
        geaendert_von    INTEGER REFERENCES nutzer (id),
        geaendert_am     TEXT
    );

    CREATE TABLE aufgaben (
        id               INTEGER PRIMARY KEY,
        garten_id        INTEGER NOT NULL REFERENCES gaerten (id) ON DELETE CASCADE,
        bestand_id       INTEGER NOT NULL REFERENCES bestand (id) ON DELETE CASCADE,
        anleitung_id     INTEGER REFERENCES anleitungen (id) ON DELETE SET NULL,
        titel            TEXT NOT NULL,
        hinweis          TEXT NOT NULL DEFAULT '',
        faellig_am       TEXT NOT NULL,
        intervall_monate INTEGER,
        fest_jetzt       INTEGER NOT NULL DEFAULT 0,
        erledigt_am      TEXT,
        erledigt_von     INTEGER REFERENCES nutzer (id),
        erstellt_von     INTEGER REFERENCES nutzer (id),
        erstellt_am      TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX aufgaben_offen ON aufgaben (garten_id, erledigt_am);

    CREATE TABLE eintraege (
        id           INTEGER PRIMARY KEY,
        garten_id    INTEGER NOT NULL REFERENCES gaerten (id) ON DELETE CASCADE,
        bestand_id   INTEGER NOT NULL REFERENCES bestand (id) ON DELETE CASCADE,
        typ          TEXT NOT NULL CHECK (typ IN ('massnahme', 'beobachtung', 'wissen', 'frage', 'antwort', 'zustand')),
        unterart     TEXT NOT NULL DEFAULT '',
        titel        TEXT NOT NULL DEFAULT '',
        text         TEXT NOT NULL DEFAULT '',
        datum        TEXT NOT NULL,
        zustand      INTEGER CHECK (zustand BETWEEN 1 AND 5),
        aufgabe_id   INTEGER REFERENCES aufgaben (id) ON DELETE SET NULL,
        antwort_auf  INTEGER REFERENCES eintraege (id) ON DELETE CASCADE,
        offen        INTEGER NOT NULL DEFAULT 0,
        erstellt_von INTEGER REFERENCES nutzer (id),
        erstellt_am  TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX eintraege_bestand ON eintraege (bestand_id, datum);

    CREATE TABLE medien (
        id           INTEGER PRIMARY KEY,
        bestand_id   INTEGER NOT NULL REFERENCES bestand (id) ON DELETE CASCADE,
        eintrag_id   INTEGER REFERENCES eintraege (id) ON DELETE CASCADE,
        aufgabe_id   INTEGER REFERENCES aufgaben (id) ON DELETE SET NULL,
        art          TEXT NOT NULL CHECK (art IN ('bild', 'video')),
        datei        TEXT NOT NULL,
        vorschau     TEXT,
        kennzeichen  TEXT NOT NULL DEFAULT '' CHECK (kennzeichen IN ('', 'vorher', 'nachher')),
        groesse      INTEGER NOT NULL DEFAULT 0,
        erstellt_von INTEGER REFERENCES nutzer (id),
        erstellt_am  TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX medien_bestand ON medien (bestand_id);
    CREATE INDEX medien_eintrag ON medien (eintrag_id);
    """,
    # 3: Merkt sich, welche Formulare schon angekommen sind. Schickt das Handy dasselbe Formular
    # nach einer wackeligen Verbindung ein zweites Mal, entsteht kein doppelter Eintrag.
    """
    CREATE TABLE gesendet (
        schluessel  TEXT PRIMARY KEY,
        antwort     TEXT NOT NULL,
        erstellt_am TEXT NOT NULL DEFAULT (datetime('now'))
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
    con = verbinden(app.config["DATENBANK"])
    con.execute("DELETE FROM gesendet WHERE erstellt_am < datetime('now', '-60 days')")
    con.commit()
    con.close()
    app.teardown_appcontext(_schliessen)
    app.cli.add_command(sicherung)
