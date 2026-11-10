"""Gärten anlegen, ändern, die gespeicherte Kartenansicht und die eigene Gartenfläche."""

import json

from flask import Blueprint, current_app, g, jsonify, redirect, render_template, request, session, url_for

from .db import hole_db
from .fehler import Eingabefehler
from .geo import grenze_aus_flurstuecken, lade_flurstuecke, pruefe_geometrie, umriss

bp = Blueprint("gaerten", __name__)

MAX_FLURSTUECKE = 30

QUELLEN = {
    "luftbild": "Luftbild © LGLN (2026), CC BY 4.0",
    "strasse": "© OpenStreetMap-Mitwirkende",
    "flurstuecke": "Flurstücke © LGLN, CC BY 4.0",
}


def aktueller_garten():
    """Der Garten, in dem gerade gearbeitet wird. Solange es nur einen gibt, ist es dieser."""
    db = hole_db()
    zeile = None
    if session.get("garten_id"):
        zeile = db.execute("SELECT * FROM gaerten WHERE id = ?", (session["garten_id"],)).fetchone()
    if zeile is None:
        zeile = db.execute("SELECT * FROM gaerten ORDER BY id LIMIT 1").fetchone()
    return zeile


def flaeche_des_gartens(zeile) -> float:
    """Die eigene Fläche zählt, wenn eine gezeichnet wurde. Sonst die amtliche Fläche der Flurstücke."""
    return zeile["eigene_m2"] if zeile["eigene_flaeche"] else zeile["flaeche_m2"]


def als_daten(zeile) -> dict:
    """Ein Garten so, wie ihn die Karte am Handy braucht."""
    flurstuecke = json.loads(zeile["grenze"]) if zeile["grenze"] else None
    eigene = json.loads(zeile["eigene_flaeche"]) if zeile["eigene_flaeche"] else None
    if eigene:
        # Die gezeichnete Fläche ist die Grenze. Die Flurstücke bleiben als dünne Linie sichtbar.
        grenze = {"type": "MultiPolygon", "coordinates": [eigene["coordinates"]]}
    else:
        grenze = flurstuecke
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
        "umriss_flurstuecke": umriss(flurstuecke) if eigene and flurstuecke else [],
        "eigene_flaeche": eigene,
        "flaeche_m2": flaeche_des_gartens(zeile),
        "ansicht": ansicht,
    }


def bestand_fuer_karte(garten_id: int) -> list[dict]:
    zeilen = hole_db().execute(
        "SELECT b.*, (SELECT vorschau FROM medien m WHERE m.bestand_id = b.id AND m.art = 'bild'"
        " ORDER BY m.id DESC LIMIT 1) AS bild,"
        " (SELECT COUNT(*) FROM aufgaben a WHERE a.bestand_id = b.id AND a.erledigt_am IS NULL) AS offen"
        " FROM bestand b WHERE b.garten_id = ? AND b.archiviert = 0",
        (garten_id,),
    ).fetchall()
    return [
        {"id": z["id"], "name": z["name"], "art": z["art"], "kategorie": z["kategorie"], "form": z["form"],
         "geometrie": json.loads(z["geometrie"]), "lat": z["lat"], "lon": z["lon"], "zustand": z["zustand"],
         "offen": z["offen"], "bild": url_for("eintraege.datei", datei=z["bild"]) if z["bild"] else None,
         "adresse": url_for("bestand.detail", bestand_id=z["id"])}
        for z in zeilen
    ]


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
        "bestand": bestand_fuer_karte(garten["id"]) if garten is not None else [],
    }


def _hole_oder_404(garten_id: int):
    zeile = hole_db().execute("SELECT * FROM gaerten WHERE id = ?", (garten_id,)).fetchone()
    if zeile is None:
        raise Eingabefehler("Diesen Garten gibt es nicht.", 404)
    return zeile


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
    zeile = hole_db().execute("SELECT * FROM gaerten WHERE id = ?", (garten_id,)).fetchone()
    if zeile is None:
        return render_template("fehler.html", titel="Garten nicht gefunden", text="Diesen Garten gibt es nicht."), 404
    return render_template(
        "garten_form.html",
        garten=als_daten(zeile),
        daten=karten_daten(zeile),
        ziel=url_for("gaerten.aendern", garten_id=garten_id),
        methode="PUT",
    )


@bp.get("/garten/flaeche")
def flaeche():
    """Eigene Gartenfläche zeichnen oder abgehen, wenn das Flurstück nicht passt."""
    garten = aktueller_garten()
    if garten is None:
        return redirect(url_for("gaerten.neu"))
    eigene = json.loads(garten["eigene_flaeche"]) if garten["eigene_flaeche"] else None
    return render_template(
        "garten_flaeche.html", garten=garten, hat_eigene=eigene is not None,
        daten={**karten_daten(garten), "start": None, "geometrie": eigene, "form": "flaeche"},
    )


@bp.post("/api/gaerten")
def anlegen():
    name, adresse, kennzeichen, grenze, flaeche_m2 = _lies_eingabe()
    db = hole_db()
    cur = db.execute(
        "INSERT INTO gaerten (name, adresse, flurstuecke, grenze, flaeche_m2, erstellt_von) VALUES (?, ?, ?, ?, ?, ?)",
        (name, adresse, json.dumps(kennzeichen), json.dumps(grenze), flaeche_m2, g.nutzer["id"]),
    )
    db.commit()
    session["garten_id"] = cur.lastrowid
    return jsonify(id=cur.lastrowid, weiter=url_for("seiten.karte")), 201


@bp.put("/api/gaerten/<int:garten_id>")
def aendern(garten_id: int):
    zeile = _hole_oder_404(garten_id)
    name, adresse, kennzeichen, grenze, flaeche_m2 = _lies_eingabe()
    db = hole_db()
    db.execute(
        "UPDATE gaerten SET name = ?, adresse = ?, flurstuecke = ?, grenze = ?, flaeche_m2 = ?,"
        " geaendert_am = datetime('now') WHERE id = ?",
        (name, adresse, json.dumps(kennzeichen), json.dumps(grenze), flaeche_m2, garten_id),
    )
    if set(kennzeichen) != set(json.loads(zeile["flurstuecke"])):
        # Neue Grenze: die alte Startansicht passt nicht mehr, die Karte zeigt wieder den ganzen Garten.
        db.execute(
            "UPDATE gaerten SET ansicht_lat = NULL, ansicht_lon = NULL, ansicht_zoom = NULL WHERE id = ?",
            (garten_id,),
        )
    db.commit()
    return jsonify(id=garten_id, weiter=url_for("seiten.karte"))


@bp.post("/api/gaerten/<int:garten_id>/flaeche")
def flaeche_speichern(garten_id: int):
    _hole_oder_404(garten_id)
    db = hole_db()
    if request.form.get("entfernen") == "1":
        db.execute(
            "UPDATE gaerten SET eigene_flaeche = NULL, eigene_m2 = NULL, eigener_umfang = NULL WHERE id = ?",
            (garten_id,),
        )
        db.commit()
        return jsonify(weiter=url_for("seiten.karte"))
    try:
        w = pruefe_geometrie(
            json.loads(request.form.get("geometrie", "")), lade_flurstuecke(current_app.config["FLURSTUECKE"]).rahmen
        )
    except (ValueError, TypeError):
        w = None
    if w is None or w["form"] != "flaeche":
        raise Eingabefehler("Eine Fläche braucht mindestens drei Punkte.")
    db.execute(
        "UPDATE gaerten SET eigene_flaeche = ?, eigene_m2 = ?, eigener_umfang = ?, ansicht_lat = NULL,"
        " ansicht_lon = NULL, ansicht_zoom = NULL, geaendert_am = datetime('now') WHERE id = ?",
        (json.dumps(w["geometrie"]), w["mass"], w["umfang"], garten_id),
    )
    db.commit()
    return jsonify(weiter=url_for("seiten.karte"), flaeche_m2=w["mass"], umfang_m=w["umfang"])


@bp.put("/api/gaerten/<int:garten_id>/ansicht")
def ansicht_speichern(garten_id: int):
    _hole_oder_404(garten_id)
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
    _hole_oder_404(garten_id)
    db = hole_db()
    db.execute(
        "UPDATE gaerten SET ansicht_lat = NULL, ansicht_lon = NULL, ansicht_zoom = NULL WHERE id = ?", (garten_id,)
    )
    db.commit()
    return jsonify(ansicht=None)
