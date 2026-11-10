import re

import pytest
from werkzeug.security import generate_password_hash

from garten import create_app
from garten.db import verbinden

PASSWORT = "ein-langes-testpasswort"


@pytest.fixture
def app(tmp_path):
    app = create_app({"DATEN": tmp_path, "TESTING": True, "SPERRE_MINUTEN": 15})
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
