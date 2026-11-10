"""Anmeldung, Sitzung, Schutz vor fremden Formularen (CSRF) und Rechte."""

import hashlib
import secrets
import sys
from datetime import datetime, timedelta, timezone
from functools import wraps
from getpass import getpass
from urllib.parse import urlsplit

import click
from flask import (
    Blueprint,
    Flask,
    abort,
    current_app,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask.cli import with_appcontext
from werkzeug.security import check_password_hash, generate_password_hash

from .db import hole_db, verbinden

bp = Blueprint("anmeldung", __name__)

MIN_PASSWORT = 10
# Ohne Anmeldung erreichbar. Statische Dateien enthalten keine Gartendaten.
OFFEN = {"anmeldung.anmelden", "static", "seiten.health", "seiten.manifest", "seiten.sw", "seiten.offline",
         "aufgaben.kalender_datei"}
# Wird geprüft, wenn es den Benutzernamen nicht gibt, damit die Antwort gleich lange dauert.
_LEERER_HASH = generate_password_hash(secrets.token_hex(16))


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


def _kennung(passwort_hash: str) -> str:
    """Kurzer Abdruck des Passworts. Ändert sich das Passwort, enden alle alten Sitzungen."""
    return hashlib.sha256(passwort_hash.encode()).hexdigest()[:16]


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


def _will_json() -> bool:
    return request.path.startswith("/api/") or request.path.startswith("/kacheln/")


def _lade_nutzer() -> None:
    g.nutzer = None
    nutzer_id = session.get("nutzer_id")
    if nutzer_id is None:
        return
    zeile = hole_db().execute("SELECT * FROM nutzer WHERE id = ?", (nutzer_id,)).fetchone()
    if zeile is None or not zeile["passwort_hash"] or session.get("pw") != _kennung(zeile["passwort_hash"]):
        session.clear()
        return
    g.nutzer = zeile


def _pruefen():
    _lade_nutzer()
    angemeldet = g.nutzer is not None

    # Zuerst die Anmeldung. Ein Handy, das nach abgelaufener Sitzung etwas nachsendet, bekommt so
    # die klare Antwort „nicht angemeldet“ und behält den Eintrag, bis man sich neu angemeldet hat.
    if not angemeldet and request.endpoint not in OFFEN:
        if _will_json():
            return jsonify(fehler="Nicht angemeldet."), 401
        weiter = request.full_path.rstrip("?") if request.method == "GET" else None
        return redirect(url_for("anmeldung.anmelden", weiter=weiter if weiter != "/" else None))

    # Nur Angemeldete laden Fotos und Videos hoch. Alle anderen schicken höchstens das Anmeldeformular.
    if not angemeldet and (request.content_length or 0) > 64 * 1024:
        abort(413)

    if request.method not in ("GET", "HEAD", "OPTIONS"):
        gesendet = request.headers.get("X-CSRF-Token") or request.form.get("csrf", "")
        erwartet = session.get("csrf", "")
        if not erwartet or not secrets.compare_digest(gesendet, erwartet):
            if _will_json():
                return jsonify(fehler="Die Sitzung ist abgelaufen. Bitte die Seite neu laden."), 400
            abort(400, "Die Sitzung ist abgelaufen. Bitte die Seite neu laden.")
    return None


def nur_meister(ansicht):
    """Für Aktionen, die nur der Meister darf (ab Stufe 3: Anleitungen, feste Priorität)."""

    @wraps(ansicht)
    def geprueft(*args, **kwargs):
        if g.nutzer["rolle"] != "meister":
            if _will_json():
                return jsonify(fehler="Das darf nur der Meister."), 403
            abort(403)
        return ansicht(*args, **kwargs)

    return geprueft


def _sicheres_ziel(ziel: str | None) -> str:
    """Nur Wege innerhalb der App, damit die Anmeldung nicht auf fremde Seiten umleitet."""
    if ziel:
        teile = urlsplit(ziel)
        if not teile.scheme and not teile.netloc and ziel.startswith("/") and not ziel.startswith("//"):
            return ziel
    return url_for("seiten.start")


@bp.route("/anmelden", methods=["GET", "POST"])
def anmelden():
    if g.nutzer is not None:
        return redirect(_sicheres_ziel(request.args.get("weiter")))
    fehler = None
    name = ""
    if request.method == "POST":
        name = request.form.get("benutzername", "").strip().lower()
        passwort = request.form.get("passwort", "")
        fehler = _anmelden(name, passwort)
        if fehler is None:
            return redirect(_sicheres_ziel(request.form.get("weiter")), code=303)
    antwort = render_template(
        "anmelden.html", fehler=fehler, benutzername=name, weiter=request.values.get("weiter", "")
    )
    return antwort, (401 if fehler else 200)


def _anmelden(name: str, passwort: str) -> str | None:
    """Meldet an und gibt None zurück, sonst den Fehlertext."""
    db = hole_db()
    falsch = "Benutzername oder Passwort stimmt nicht."
    zeile = db.execute("SELECT * FROM nutzer WHERE benutzername = ?", (name,)).fetchone()
    if zeile is None:
        check_password_hash(_LEERER_HASH, passwort)
        return falsch

    if zeile["gesperrt_bis"]:
        bis = datetime.fromisoformat(zeile["gesperrt_bis"])
        if bis > _jetzt():
            minuten = max(1, round((bis - _jetzt()).total_seconds() / 60))
            return f"Zu viele Fehlversuche. Bitte in {minuten} Minuten noch einmal versuchen."

    if not zeile["passwort_hash"]:
        check_password_hash(_LEERER_HASH, passwort)
        return "Für dieses Konto ist noch kein Passwort gesetzt."

    if not check_password_hash(zeile["passwort_hash"], passwort):
        versuche = zeile["fehlversuche"] + 1
        gesperrt_bis = None
        if versuche >= current_app.config["MAX_FEHLVERSUCHE"]:
            gesperrt_bis = (_jetzt() + timedelta(minutes=current_app.config["SPERRE_MINUTEN"])).isoformat()
            versuche = 0
        db.execute(
            "UPDATE nutzer SET fehlversuche = ?, gesperrt_bis = ? WHERE id = ?",
            (versuche, gesperrt_bis, zeile["id"]),
        )
        db.commit()
        return falsch

    db.execute("UPDATE nutzer SET fehlversuche = 0, gesperrt_bis = NULL WHERE id = ?", (zeile["id"],))
    db.commit()
    session.clear()
    session.permanent = True
    session["nutzer_id"] = zeile["id"]
    session["pw"] = _kennung(zeile["passwort_hash"])
    csrf_token()
    return None


@bp.post("/abmelden")
def abmelden():
    session.clear()
    return redirect(url_for("anmeldung.anmelden"), code=303)


@click.command("passwort")
@click.argument("benutzername")
@with_appcontext
def passwort_setzen(benutzername: str):
    """Setzt das Passwort für sven oder johannes.

    Das Passwort wird verdeckt abgefragt oder aus der Standardeingabe gelesen.
    Es steht nie auf der Kommandozeile und nie im Protokoll.
    """
    con = verbinden(current_app.config["DATENBANK"])
    try:
        zeile = con.execute("SELECT id FROM nutzer WHERE benutzername = ?", (benutzername,)).fetchone()
        if zeile is None:
            namen = ", ".join(z[0] for z in con.execute("SELECT benutzername FROM nutzer ORDER BY id"))
            raise click.ClickException(f"Den Benutzer „{benutzername}“ gibt es nicht. Vorhanden: {namen}.")
        if sys.stdin.isatty():
            passwort = getpass("Neues Passwort: ")
            if passwort != getpass("Passwort wiederholen: "):
                raise click.ClickException("Die beiden Eingaben stimmen nicht überein.")
        else:
            passwort = sys.stdin.readline().rstrip("\r\n")
        if len(passwort) < MIN_PASSWORT:
            raise click.ClickException(f"Das Passwort braucht mindestens {MIN_PASSWORT} Zeichen.")
        con.execute(
            "UPDATE nutzer SET passwort_hash = ?, fehlversuche = 0, gesperrt_bis = NULL WHERE id = ?",
            (generate_password_hash(passwort), zeile["id"]),
        )
        con.commit()
    finally:
        con.close()
    click.echo(f"Passwort für {benutzername} gesetzt. Bestehende Anmeldungen sind beendet.")


def einrichten(app: Flask) -> None:
    app.before_request(_pruefen)
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.cli.add_command(passwort_setzen)
