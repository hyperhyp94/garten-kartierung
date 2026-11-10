"""Die Seiten der App und alles, was jede Antwort betrifft."""

from flask import (
    Blueprint,
    Flask,
    current_app,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.exceptions import HTTPException

from . import VERSION
from .gaerten import aktueller_garten, karten_daten

bp = Blueprint("seiten", __name__)

def _mit_garten(vorlage: str, **werte):
    garten = aktueller_garten()
    if garten is None:
        return redirect(url_for("gaerten.neu"))
    return render_template(vorlage, garten=garten, **werte)


@bp.get("/")
def start():
    # Ab Stufe 3 ist „Heute“ die Startseite. Bis dahin ist es die Karte.
    return redirect(url_for("seiten.karte"))


@bp.get("/karte")
def karte():
    garten = aktueller_garten()
    if garten is None:
        return redirect(url_for("gaerten.neu"))
    return render_template("karte.html", garten=garten, daten=karten_daten(garten))


@bp.get("/heute")
def heute():
    return _mit_garten("heute.html")


@bp.get("/bestand")
def bestand():
    return _mit_garten("bestand.html")


@bp.get("/mehr")
def mehr():
    return _mit_garten("mehr.html")


@bp.get("/health")
def health():
    return jsonify(status="ok", version=VERSION)


@bp.get("/manifest.webmanifest")
def manifest():
    return send_from_directory(current_app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json")


@bp.get("/sw.js")
def sw():
    # Der Service Worker muss von ganz oben kommen, damit er für die ganze App gilt.
    antwort = send_from_directory(current_app.static_folder, "sw.js", mimetype="text/javascript")
    antwort.headers["Cache-Control"] = "no-cache"
    return antwort


@bp.get("/offline")
def offline():
    return render_template("offline.html")


def _kopfzeilen(antwort):
    antwort.headers.setdefault("X-Content-Type-Options", "nosniff")
    antwort.headers.setdefault("Referrer-Policy", "same-origin")
    antwort.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "img-src 'self' data: blob: https://tile.openstreetmap.org; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    )
    if request.endpoint != "static" and "Cache-Control" not in antwort.headers:
        # Seiten mit Gartendaten bleiben nicht im Zwischenspeicher fremder Geräte hängen.
        antwort.headers["Cache-Control"] = "no-store"
    return antwort


def _fehlerseite(fehler: HTTPException):
    if request.path.startswith("/api/") or request.path.startswith("/kacheln/"):
        return jsonify(fehler=fehler.description or fehler.name), fehler.code
    titel = {
        400: "Das hat nicht geklappt",
        403: "Kein Zugriff",
        404: "Seite nicht gefunden",
        413: "Die Datei ist zu groß",
    }.get(fehler.code, "Etwas ist schiefgelaufen")
    text = fehler.description if fehler.code in (400, 403) else "Bitte gehe zurück und versuche es noch einmal."
    return render_template("fehler.html", titel=titel, text=text), fehler.code


def einrichten(app: Flask) -> None:
    app.after_request(_kopfzeilen)
    app.register_error_handler(HTTPException, _fehlerseite)
    app.jinja_env.globals["version"] = VERSION

    @app.context_processor
    def _nutzer():
        return {"nutzer": g.get("nutzer")}
