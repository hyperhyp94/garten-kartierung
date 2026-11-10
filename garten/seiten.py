"""Karte, „Mehr“, die Hülle der App und alles, was jede Antwort betrifft."""

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
from .aufgaben import schoen
from .bestand import ZUSTAND
from .db import hole_db
from .fehler import Eingabefehler
from .gaerten import aktueller_garten, flaeche_des_gartens, karten_daten

bp = Blueprint("seiten", __name__)


@bp.get("/")
def start():
    return redirect(url_for("aufgaben.heute_seite"))


@bp.get("/karte")
def karte():
    garten = aktueller_garten()
    if garten is None:
        return redirect(url_for("gaerten.neu"))
    return render_template("karte.html", garten=garten, daten=karten_daten(garten),
                           flaeche_m2=flaeche_des_gartens(garten))


@bp.get("/mehr")
def mehr():
    garten = aktueller_garten()
    if garten is None:
        return redirect(url_for("gaerten.neu"))
    return render_template("mehr.html", garten=garten, flaeche_m2=flaeche_des_gartens(garten))


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
        "img-src 'self' data: blob: https://tile.openstreetmap.org; media-src 'self' blob:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    )
    if request.endpoint != "static" and "Cache-Control" not in antwort.headers:
        # Seiten mit Gartendaten bleiben nicht im Zwischenspeicher fremder Geräte hängen.
        antwort.headers["Cache-Control"] = "no-store"
    return antwort


def _schon_angekommen():
    """Dasselbe Formular kommt ein zweites Mal: die Antwort vom ersten Mal zurückgeben, nichts neu anlegen."""
    if request.method != "POST" or not request.path.startswith("/api/"):
        return None
    schluessel = request.form.get("_schluessel", "")
    if not 8 <= len(schluessel) <= 64:
        return None
    zeile = hole_db().execute("SELECT antwort FROM gesendet WHERE schluessel = ?", (schluessel,)).fetchone()
    if zeile is not None:
        return current_app.response_class(zeile["antwort"], mimetype="application/json")
    g.sende_schluessel = schluessel
    return None


def _merke_angekommen(antwort):
    schluessel = g.pop("sende_schluessel", None)
    if schluessel and 200 <= antwort.status_code < 300 and antwort.is_json:
        db = hole_db()
        db.execute(
            "INSERT OR IGNORE INTO gesendet (schluessel, antwort) VALUES (?, ?)",
            (schluessel, antwort.get_data(as_text=True)),
        )
        db.commit()
    return antwort


def _will_json() -> bool:
    return request.path.startswith("/api/") or request.path.startswith("/kacheln/")


def _fehlerseite(fehler: HTTPException):
    if _will_json():
        text = "Die Datei ist zu groß." if fehler.code == 413 else (fehler.description or fehler.name)
        return jsonify(fehler=text), fehler.code
    titel = {
        400: "Das hat nicht geklappt",
        403: "Kein Zugriff",
        404: "Seite nicht gefunden",
        413: "Die Datei ist zu groß",
    }.get(fehler.code, "Etwas ist schiefgelaufen")
    text = fehler.description if fehler.code in (400, 403) else "Bitte gehe zurück und versuche es noch einmal."
    return render_template("fehler.html", titel=titel, text=text), fehler.code


def _eingabefehler(fehler: Eingabefehler):
    if _will_json():
        return jsonify(fehler=str(fehler)), fehler.status
    return render_template("fehler.html", titel="Das hat nicht geklappt", text=str(fehler)), fehler.status


def _zahl(wert, stellen: int = 0) -> str:
    """1317.4 wird zu „1.317“, mit einer Stelle zu „1.317,4“."""
    text = f"{wert:,.{stellen}f}"
    return text.replace(",", "§").replace(".", ",").replace("§", ".")


def einrichten(app: Flask) -> None:
    app.before_request(_schon_angekommen)
    app.after_request(_merke_angekommen)
    app.after_request(_kopfzeilen)
    app.register_error_handler(HTTPException, _fehlerseite)
    app.register_error_handler(Eingabefehler, _eingabefehler)
    app.jinja_env.globals["version"] = VERSION
    app.jinja_env.globals["zustand_worte"] = ZUSTAND
    app.jinja_env.filters["datum"] = schoen
    app.jinja_env.filters["zahl"] = _zahl

    @app.context_processor
    def _nutzer():
        nutzer = g.get("nutzer")
        return {"nutzer": nutzer, "ist_meister": bool(nutzer and nutzer["rolle"] == "meister")}
