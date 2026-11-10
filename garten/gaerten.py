"""Gärten anlegen, ändern und die gespeicherte Kartenansicht."""

import json

from flask import Blueprint, current_app, g, jsonify, render_template, request, session, url_for

from .db import hole_db
from .geo import grenze_aus_flurstuecken, lade_flurstuecke, umriss

bp = Blueprint("gaerten", __name__)

MAX_FLURSTUECKE = 30


class Eingabefehler(ValueError):
    """Eine Eingabe passt nicht. Der Text wird dem Nutzer gezeigt."""


@bp.errorhandler(Eingabefehler)
def _eingabefehler(fehler):
    return jsonify(fehler=str(fehler)), 422


def aktueller_garten():
    """Der Garten, in dem gerade gearbeitet wird. Solange es nur einen gibt, ist es dieser."""
    db = hole_db()
    zeile = None
    if session.get("garten_id"):
        zeile = db.execute("SELECT * FROM gaerten WHERE id = ?", (session["garten_id"],)).fetchone()
    if zeile is None:
        zeile = db.execute("SELECT * FROM gaerten ORDER BY id LIMIT 1").fetchone()
    return zeile


def als_daten(zeile) -> dict:
    """Ein Garten so, wie ihn die Karte am Handy braucht."""
    grenze = json.loads(zeile["grenze"]) if zeile["grenze"] else None
    ansicht = None
    if zeile["ansicht_zoom"] is not None:
        ansicht = {"lat": zeile["ansicht_lat"], "lon": zeile["ansicht_lon"], "zoom": zeile["ansicht_zoom"]}
    return {
        "id": zeile["id"],
        "name": zeile["name"],
        "adresse": zeile["adresse"],
        "flurstuecke": json.loads(zeile["flurstuecke"]),
        "grenze": grenze,
        "umriss": umriss(grenze) if grenze else [],
        "flaeche_m2": zeile["flaeche_m2"],
        "ansicht": ansicht,
    }


QUELLEN = {
    "luftbild": "Luftbild © LGLN (2026), CC BY 4.0",
    "strasse": "© OpenStreetMap-Mitwirkende",
    "flurstuecke": "Flurstücke © LGLN, CC BY 4.0",
}


def karten_daten(garten) -> dict:
    """Alles, was die Karte am Handy zum Start braucht."""
    gebiet = lade_flurstuecke(current_app.config["FLURSTUECKE"]).rahmen
    return {
        "gebiet": gebiet,
        "luftbild": "/kacheln/luftbild/{z}/{x}/{y}.jpg",
        "strasse": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "flurstuecke": url_for("karte.flurstuecke"),
        "quellen": QUELLEN,
        "garten": als_daten(garten) if garten is not None else None,
    }


def _hole_oder_404(garten_id: int):
    zeile = hole_db().execute("SELECT * FROM gaerten WHERE id = ?", (garten_id,)).fetchone()
    if zeile is None:
        return None, (jsonify(fehler="Diesen Garten gibt es nicht."), 404)
    return zeile, None


def _lies_eingabe() -> tuple[str, str, list[str], dict, float]:
    daten = request.get_json(silent=True)
    if not isinstance(daten, dict):
        raise Eingabefehler("Die Eingabe konnte nicht gelesen werden.")
    name = str(daten.get("name", "")).strip()
    adresse = str(daten.get("adresse", "")).strip()
    kennzeichen = daten.get("flurstuecke")
    if not name:
        raise Eingabefehler("Bitte einen Namen für den Garten eingeben.")
    if len(name) > 80 or len(adresse) > 200:
        raise Eingabefehler("Name oder Adresse ist zu lang.")
    if not isinstance(kennzeichen, list) or not all(isinstance(k, str) for k in kennzeichen):
        raise Eingabefehler("Die Auswahl der Flurstücke konnte nicht gelesen werden.")
    kennzeichen = list(dict.fromkeys(kennzeichen))
    if not kennzeichen:
        raise Eingabefehler("Bitte mindestens ein Flurstück auf der Karte antippen.")
    if len(kennzeichen) > MAX_FLURSTUECKE:
        raise Eingabefehler(f"Höchstens {MAX_FLURSTUECKE} Flurstücke pro Garten.")
    try:
        grenze, flaeche = grenze_aus_flurstuecken(lade_flurstuecke(current_app.config["FLURSTUECKE"]), kennzeichen)
    except KeyError:
        raise Eingabefehler("Ein gewähltes Flurstück ist nicht bekannt.") from None
    return name, adresse, kennzeichen, grenze, flaeche


@bp.get("/garten/neu")
def neu():
    return render_template(
        "garten_form.html", garten=None, daten=karten_daten(None), ziel=url_for("gaerten.anlegen"), methode="POST"
    )


@bp.get("/garten/<int:garten_id>/bearbeiten")
def bearbeiten(garten_id: int):
    zeile, _ = _hole_oder_404(garten_id)
    if zeile is None:
        return render_template("fehler.html", titel="Garten nicht gefunden", text="Diesen Garten gibt es nicht."), 404
    return render_template(
        "garten_form.html",
        garten=als_daten(zeile),
        daten=karten_daten(zeile),
        ziel=url_for("gaerten.aendern", garten_id=garten_id),
        methode="PUT",
    )


@bp.post("/api/gaerten")
def anlegen():
    name, adresse, kennzeichen, grenze, flaeche = _lies_eingabe()
    db = hole_db()
    cur = db.execute(
        "INSERT INTO gaerten (name, adresse, flurstuecke, grenze, flaeche_m2, erstellt_von) VALUES (?, ?, ?, ?, ?, ?)",
        (name, adresse, json.dumps(kennzeichen), json.dumps(grenze), flaeche, g.nutzer["id"]),
    )
    db.commit()
    session["garten_id"] = cur.lastrowid
    return jsonify(id=cur.lastrowid, weiter=url_for("seiten.karte")), 201


@bp.put("/api/gaerten/<int:garten_id>")
def aendern(garten_id: int):
    zeile, fehler = _hole_oder_404(garten_id)
    if fehler:
        return fehler
    name, adresse, kennzeichen, grenze, flaeche = _lies_eingabe()
    db = hole_db()
    db.execute(
        "UPDATE gaerten SET name = ?, adresse = ?, flurstuecke = ?, grenze = ?, flaeche_m2 = ?,"
        " geaendert_am = datetime('now') WHERE id = ?",
        (name, adresse, json.dumps(kennzeichen), json.dumps(grenze), flaeche, garten_id),
    )
    if set(kennzeichen) != set(json.loads(zeile["flurstuecke"])):
        # Neue Grenze: die alte Startansicht passt nicht mehr, die Karte zeigt wieder den ganzen Garten.
        db.execute(
            "UPDATE gaerten SET ansicht_lat = NULL, ansicht_lon = NULL, ansicht_zoom = NULL WHERE id = ?",
            (garten_id,),
        )
    db.commit()
    return jsonify(id=garten_id, weiter=url_for("seiten.karte"))


@bp.put("/api/gaerten/<int:garten_id>/ansicht")
def ansicht_speichern(garten_id: int):
    _, fehler = _hole_oder_404(garten_id)
    if fehler:
        return fehler
    daten = request.get_json(silent=True) or {}
    try:
        lat, lon, zoom = float(daten["lat"]), float(daten["lon"]), float(daten["zoom"])
    except (KeyError, TypeError, ValueError):
        raise Eingabefehler("Die Kartenansicht konnte nicht gelesen werden.") from None
    west, sued, ost, nord = lade_flurstuecke(current_app.config["FLURSTUECKE"]).rahmen
    rand = 0.05
    if not (west - rand <= lon <= ost + rand and sued - rand <= lat <= nord + rand and 10 <= zoom <= 22):
        raise Eingabefehler("Diese Kartenansicht liegt außerhalb von Feggendorf.")
    db = hole_db()
    db.execute(
        "UPDATE gaerten SET ansicht_lat = ?, ansicht_lon = ?, ansicht_zoom = ?, geaendert_am = datetime('now')"
        " WHERE id = ?",
        (lat, lon, zoom, garten_id),
    )
    db.commit()
    return jsonify(ansicht={"lat": lat, "lon": lon, "zoom": zoom})


@bp.delete("/api/gaerten/<int:garten_id>/ansicht")
def ansicht_zuruecksetzen(garten_id: int):
    _, fehler = _hole_oder_404(garten_id)
    if fehler:
        return fehler
    db = hole_db()
    db.execute(
        "UPDATE gaerten SET ansicht_lat = NULL, ansicht_lon = NULL, ansicht_zoom = NULL WHERE id = ?", (garten_id,)
    )
    db.commit()
    return jsonify(ansicht=None)
