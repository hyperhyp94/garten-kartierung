import io
import json
import re
from datetime import date

import pytest
from werkzeug.security import generate_password_hash

from garten import create_app
from garten.db import verbinden

PASSWORT = "ein-langes-testpasswort"
HEUTE = date(2027, 1, 15)  # fester Stichtag, damit Fälligkeiten in den Tests nicht wandern
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200  # reicht dem Server als Foto
ORT = {"type": "Point", "coordinates": [9.3835, 52.2850]}


@pytest.fixture
def app(tmp_path):
    app = create_app({"DATEN": tmp_path, "TESTING": True, "SPERRE_MINUTEN": 15, "HEUTE": HEUTE})
    con = verbinden(app.config["DATENBANK"])
    con.execute("UPDATE nutzer SET passwort_hash = ?", (generate_password_hash(PASSWORT),))
    con.commit()
    con.close()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client, pfad="/anmelden"):
    seite = client.get(pfad, follow_redirects=True).get_data(as_text=True)
    return re.search(r'name="csrf" content="([^"]+)"', seite).group(1)


def melde_an(client, name="sven", passwort=PASSWORT):
    return client.post("/anmelden", data={"benutzername": name, "passwort": passwort, "csrf": csrf(client)})


@pytest.fixture
def sven(client):
    assert melde_an(client).status_code == 303
    client.kopf = {"X-CSRF-Token": csrf(client, "/mehr")}
    return client


FLURSTUECK = "034819001000560007__"  # 56/7, Flur 1, 1317 m²
NACHBAR = "034819001000680020__"  # 68/20, Flur 1, 1471 m²


@pytest.fixture
def garten(sven):
    antwort = sven.post(
        "/api/gaerten",
        json={"name": "Testgarten", "adresse": "Deisterstraße 40", "flurstuecke": [FLURSTUECK]},
        headers=sven.kopf,
    )
    assert antwort.status_code == 201
    return antwort.get_json()["id"]


def foto(name="foto.jpg", inhalt=JPEG):
    return (io.BytesIO(inhalt), name)


def sende(client, pfad, daten=None):
    """Schickt ein Formular so ab, wie es das Handy tut."""
    return client.post(pfad, data=daten or {}, headers=client.kopf, content_type="multipart/form-data")


def lege_pflanze_an(client, **werte):
    daten = {"art": "pflanze", "name": "Apfelbaum", "kategorie": "Obst", "geometrie": json.dumps(ORT), **werte}
    antwort = sende(client, "/api/bestand", daten)
    assert antwort.status_code == 201, antwort.get_json()
    return antwort.get_json()["id"]


@pytest.fixture
def pflanze(sven, garten):
    return lege_pflanze_an(sven)


@pytest.fixture
def johannes(app, garten):
    client = app.test_client()
    assert melde_an(client, name="johannes").status_code == 303
    client.kopf = {"X-CSRF-Token": csrf(client, "/mehr")}
    return client
