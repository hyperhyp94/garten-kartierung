import gzip
import json

import pytest

from garten import karte
from garten.geo import kachel_fuer, kachel_rahmen, lade_flurstuecke, umriss

BILD = b"\xff\xd8\xff\xe0" + b"\x00" * 64  # sieht für die Prüfung wie ein JPEG aus


def test_flurstuecke_vollstaendig(sven):
    antwort = sven.get("/api/flurstuecke")
    assert antwort.status_code == 200
    assert antwort.headers["Content-Encoding"] == "gzip"
    sammlung = json.loads(gzip.decompress(antwort.data))
    assert len(sammlung["features"]) == 663
    erstes = sammlung["features"][0]["properties"]
    assert erstes == {"k": "034819001000560007__", "nr": "56/7", "flur": 1, "m2": 1317.0}
    # Zweiter Abruf mit bekanntem Stand: nichts wird erneut übertragen.
    assert sven.get("/api/flurstuecke", headers={"If-None-Match": antwort.headers["ETag"]}).status_code == 304


def test_umriss_laesst_gemeinsame_kanten_weg():
    a = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
    b = [[1, 0], [2, 0], [2, 1], [1, 1], [1, 0]]  # teilt die Kante x=1 mit a
    kanten = umriss({"type": "MultiPolygon", "coordinates": [[a], [b]]})
    assert len(kanten) == 6
    assert [[1, 0], [1, 1]] not in kanten and [[1, 1], [1, 0]] not in kanten


def test_kachel_rechnung():
    # Kachel 0/0/0 ist die ganze Welt.
    west, sued, ost, nord = kachel_rahmen(0, 0, 0)
    assert west == pytest.approx(-20037508.34, abs=0.01) and nord == pytest.approx(20037508.34, abs=0.01)
    assert ost == -west and sued == -nord
    # Der Garten in Feggendorf liegt bei Zoom 17 in dieser Kachel.
    assert kachel_fuer(9.3835, 52.2850, 17) == (68952, 43125)


def kachel_im_ort(app, z=18):
    west, sued, ost, nord = lade_flurstuecke(app.config["FLURSTUECKE"]).rahmen
    return z, *kachel_fuer((west + ost) / 2, (sued + nord) / 2, z)


def test_luftbild_wird_einmal_geholt_und_dann_gespeichert(app, sven, monkeypatch):
    abrufe = []
    monkeypatch.setattr(karte, "hole_luftbild", lambda z, x, y: abrufe.append((z, x, y)) or BILD)
    z, x, y = kachel_im_ort(app)

    erste = sven.get(f"/kacheln/luftbild/{z}/{x}/{y}.jpg")
    assert erste.status_code == 200
    assert erste.data == BILD
    assert erste.mimetype == "image/jpeg"
    assert "immutable" in erste.headers["Cache-Control"]
    erste.close()

    zweite = sven.get(f"/kacheln/luftbild/{z}/{x}/{y}.jpg")
    assert zweite.data == BILD
    zweite.close()
    assert abrufe == [(z, x, y)]
    assert (app.config["DATEN"] / "kacheln" / "luftbild" / str(z) / str(x) / f"{y}.jpg").read_bytes() == BILD


def test_luftbild_nur_im_kartengebiet(app, sven, monkeypatch):
    monkeypatch.setattr(karte, "hole_luftbild", lambda z, x, y: pytest.fail("darf nicht abgerufen werden"))
    z, x, y = kachel_im_ort(app)
    assert sven.get(f"/kacheln/luftbild/{z}/{x + 5000}/{y}.jpg").status_code == 404  # weit weg
    assert sven.get(f"/kacheln/luftbild/21/{x * 8}/{y * 8}.jpg").status_code == 404  # zu nah
    assert sven.get("/kacheln/luftbild/5/16/10.jpg").status_code == 404  # zu weit weg gezoomt


def test_luftbild_ausfall_hinterlaesst_keine_datei(app, sven, monkeypatch):
    def kaputt(z, x, y):
        raise OSError("Dienst nicht erreichbar")

    monkeypatch.setattr(karte, "hole_luftbild", kaputt)
    z, x, y = kachel_im_ort(app)
    antwort = sven.get(f"/kacheln/luftbild/{z}/{x}/{y}.jpg")
    assert antwort.status_code == 502
    assert "nicht erreichbar" in antwort.get_json()["fehler"]
    assert not (app.config["DATEN"] / "kacheln").exists()
