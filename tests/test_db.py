import sqlite3

from garten.db import SCHRITTE, aktualisieren, verbinden


def test_schema_ist_auf_dem_neuesten_stand(app):
    con = verbinden(app.config["DATENBANK"])
    assert con.execute("PRAGMA user_version").fetchone()[0] == len(SCHRITTE)
    assert [z["benutzername"] for z in con.execute("SELECT benutzername FROM nutzer ORDER BY id")] == [
        "sven",
        "johannes",
    ]
    con.close()


def test_zweiter_start_aendert_nichts(app):
    aktualisieren(app.config["DATENBANK"])
    con = verbinden(app.config["DATENBANK"])
    assert con.execute("SELECT COUNT(*) FROM nutzer").fetchone()[0] == 2
    con.close()


def test_sicherung_ist_lesbar_und_raeumt_auf(app):
    ordner = app.config["DATEN"] / "sicherung"
    ordner.mkdir()
    for tag in range(1, 21):
        (ordner / f"garten-2020-01-{tag:02d}.db").write_bytes(b"alt")

    ergebnis = app.test_cli_runner().invoke(args=["sicherung"])
    assert ergebnis.exit_code == 0, ergebnis.output

    dateien = sorted(ordner.glob("garten-*.db"))
    assert len(dateien) == 14
    kopie = sqlite3.connect(dateien[-1])
    assert kopie.execute("SELECT COUNT(*) FROM nutzer").fetchone()[0] == 2
    kopie.close()
