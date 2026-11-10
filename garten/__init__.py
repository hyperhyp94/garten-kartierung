"""Garten-Kartierung: Web-App fürs Handy, läuft auf dem Raspberry Pi."""

import os
import secrets
import tempfile
from datetime import timedelta
from pathlib import Path

from flask import Flask, request
from flask.sessions import SecureCookieSessionInterface
from werkzeug.middleware.proxy_fix import ProxyFix

VERSION = "1.0.0"
PROJEKT = Path(__file__).resolve().parent.parent


class Sitzung(SecureCookieSessionInterface):
    """Setzt das Secure-Flag am Cookie immer dann, wenn die Anfrage über HTTPS kam.

    So funktioniert die Anmeldung im LAN (http) und über den Tunnel (https),
    ohne dass etwas umgestellt werden muss.
    """

    def get_cookie_secure(self, app):
        return request.is_secure


def _geheimer_schluessel(ordner: Path) -> bytes:
    datei = ordner / "secret_key"
    if not datei.exists():
        datei.touch(mode=0o600)
        datei.write_bytes(secrets.token_bytes(32))
    return datei.read_bytes()


def create_app(konfiguration: dict | None = None) -> Flask:
    daten = Path(os.environ.get("GARTEN_DATEN", PROJEKT / "instance"))
    if konfiguration and "DATEN" in konfiguration:
        daten = Path(konfiguration["DATEN"])
    daten.mkdir(parents=True, exist_ok=True)

    app = Flask(__name__, instance_path=str(daten))
    app.config.update(
        DATEN=daten,
        DATENBANK=daten / "garten.db",
        FLURSTUECKE=PROJEKT / "data" / "flurstuecke_feggendorf.geojson",
        # Luftbild des Landes Niedersachsen (LGLN, CC BY 4.0), 20 cm pro Bildpunkt
        LUFTBILD_WMS="https://opendata.lgln.niedersachsen.de/doorman/noauth/dop_wms",
        LUFTBILD_EBENE="ni_dop20",
        MAX_FEHLVERSUCHE=5,
        SPERRE_MINUTEN=15,
        PERMANENT_SESSION_LIFETIME=timedelta(days=90),
        SESSION_COOKIE_NAME="garten",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # Ein Video darf 200 MB groß sein, dazu kommen Fotos und Formularfelder.
        MAX_CONTENT_LENGTH=230 * 1024 * 1024,
        MAX_FORM_MEMORY_SIZE=2 * 1024 * 1024,
        JSON_AS_ASCII=False,
    )
    if konfiguration:
        app.config.update(konfiguration)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = _geheimer_schluessel(daten)

    app.session_interface = Sitzung()
    # Hinter dem Tunnel kommt die Anfrage als http an. Der Tunnel meldet im
    # Header, dass sie außen https war.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Große Uploads landen beim Empfang in einer Hilfsdatei. Die soll auf der Speicherkarte liegen und
    # nicht im Arbeitsspeicher, den manche Systeme für /tmp benutzen.
    (daten / "tmp").mkdir(exist_ok=True)
    tempfile.tempdir = str(daten / "tmp")

    from . import anmeldung, aufgaben, bestand, db, eintraege, gaerten, karte, lexikon, seiten

    db.einrichten(app)
    con = db.verbinden(app.config["DATENBANK"])
    lexikon.saee_anleitungen(con)
    con.close()
    anmeldung.einrichten(app)
    for modul in (anmeldung, seiten, gaerten, karte, bestand, eintraege, aufgaben):
        app.register_blueprint(modul.bp)
    seiten.einrichten(app)
    return app
