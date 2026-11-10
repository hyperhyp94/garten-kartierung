"""Kartendaten für das Handy: Flurstücke und Luftbildkacheln.

Das Luftbild kommt vom Land Niedersachsen. Der Dienst braucht ein bis zwei
Sekunden pro Kachel und verbietet dem Browser das Zwischenspeichern. Deshalb
holt der Pi jede Kachel nur einmal und legt sie auf die Platte. Danach kommt
sie sofort und der Dienst wird nicht unnötig belastet.
"""

import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from flask import Blueprint, Response, current_app, jsonify, request, send_file

from .geo import kachel_im_gebiet, kachel_rahmen, lade_flurstuecke

bp = Blueprint("karte", __name__)

ZOOM_MIN, ZOOM_MAX = 12, 20  # ab Zoom 20 ist das Luftbild ausgereizt, darüber vergrößert das Handy
EIN_JAHR = 365 * 24 * 3600


@bp.get("/api/flurstuecke")
def flurstuecke():
    daten = lade_flurstuecke(current_app.config["FLURSTUECKE"])
    antwort = Response(daten.json_gzip, mimetype="application/geo+json")
    antwort.headers["Content-Encoding"] = "gzip"
    antwort.headers["Cache-Control"] = "private, max-age=86400"
    antwort.set_etag(daten.etag)
    return antwort.make_conditional(request)


def hole_luftbild(z: int, x: int, y: int) -> bytes:
    """Holt eine Kachel vom Luftbild-Dienst. Wird in den Tests ersetzt."""
    west, sued, ost, nord = kachel_rahmen(z, x, y)
    abfrage = urllib.parse.urlencode(
        {
            "SERVICE": "WMS",
            "VERSION": "1.3.0",
            "REQUEST": "GetMap",
            "LAYERS": current_app.config["LUFTBILD_EBENE"],
            "STYLES": "",
            "CRS": "EPSG:3857",
            "BBOX": f"{west},{sued},{ost},{nord}",
            "WIDTH": 256,
            "HEIGHT": 256,
            "FORMAT": "image/jpeg",
        }
    )
    anfrage = urllib.request.Request(
        f"{current_app.config['LUFTBILD_WMS']}?{abfrage}", headers={"User-Agent": "garten-kartierung"}
    )
    with urllib.request.urlopen(anfrage, timeout=15) as antwort:
        inhalt = antwort.read(2 * 1024 * 1024)
        if antwort.headers.get_content_type() != "image/jpeg" or not inhalt.startswith(b"\xff\xd8"):
            raise ValueError("Der Luftbild-Dienst hat kein Bild geliefert.")
        return inhalt


@bp.get("/kacheln/luftbild/<int:z>/<int:x>/<int:y>.jpg")
def luftbild(z: int, x: int, y: int):
    gebiet = lade_flurstuecke(current_app.config["FLURSTUECKE"]).rahmen
    if not ZOOM_MIN <= z <= ZOOM_MAX or not kachel_im_gebiet(gebiet, z, x, y):
        return jsonify(fehler="Außerhalb des Kartengebiets."), 404

    ordner = current_app.config["DATEN"] / "kacheln" / "luftbild" / str(z) / str(x)
    datei = ordner / f"{y}.jpg"
    if not datei.exists():
        try:
            inhalt = hole_luftbild(z, x, y)
        except (OSError, ValueError, urllib.error.URLError) as fehler:
            current_app.logger.warning("Luftbild %s/%s/%s nicht geladen: %s", z, x, y, fehler)
            return jsonify(fehler="Das Luftbild ist gerade nicht erreichbar."), 502
        ordner.mkdir(parents=True, exist_ok=True)
        # Erst in eine Hilfsdatei schreiben, damit nie eine halbe Kachel liegen bleibt.
        fd, hilfsdatei = tempfile.mkstemp(dir=ordner, suffix=".teil")
        with os.fdopen(fd, "wb") as f:
            f.write(inhalt)
        os.replace(hilfsdatei, datei)

    antwort = send_file(datei, mimetype="image/jpeg")
    antwort.headers["Cache-Control"] = f"private, max-age={EIN_JAHR}, immutable"
    return antwort
