"""Flurstücke von Feggendorf und Rechnen mit Kartenkacheln.

Die GeoJSON-Datei im Repo ist die einzige Quelle für Flurstücke. Sie wird
einmal gelesen und im Speicher gehalten.
"""

import gzip
import hashlib
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

STELLEN = 7  # Nachkommastellen der Koordinaten, entspricht etwa einem Zentimeter
ERDHALB = 20037508.342789244  # halber Erdumfang in Web-Mercator-Metern


@dataclass(frozen=True)
class Flurstuecke:
    nach_kennzeichen: dict
    rahmen: tuple  # (west, sued, ost, nord)
    json_gzip: bytes  # verschlankte Sammlung für das Handy
    etag: str


def _runden(ringe):
    return [[[round(x, STELLEN), round(y, STELLEN)] for x, y in ring] for ring in ringe]


@lru_cache(maxsize=2)
def lade_flurstuecke(pfad: Path) -> Flurstuecke:
    roh = json.loads(Path(pfad).read_text(encoding="utf-8"))
    nach_kennzeichen = {}
    schlank = []
    west = sued = math.inf
    ost = nord = -math.inf
    for merkmal in roh["features"]:
        e = merkmal["properties"]
        polygone = [_runden(polygon) for polygon in merkmal["geometry"]["coordinates"]]
        for polygon in polygone:
            for x, y in polygon[0]:
                west, ost = min(west, x), max(ost, x)
                sued, nord = min(sued, y), max(nord, y)
        eintrag = {
            "type": "Feature",
            "properties": {
                "k": e["kennzeichen"],
                "nr": e["flurstueck"],
                "flur": int(e["flur"]),
                "m2": e["flaeche_m2"],
            },
            "geometry": {"type": "MultiPolygon", "coordinates": polygone},
        }
        nach_kennzeichen[e["kennzeichen"]] = eintrag
        schlank.append(eintrag)
    text = json.dumps(
        {"type": "FeatureCollection", "quelle": roh.get("source", ""), "features": schlank},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return Flurstuecke(
        nach_kennzeichen=nach_kennzeichen,
        rahmen=(west, sued, ost, nord),
        json_gzip=gzip.compress(text, mtime=0),
        etag=hashlib.sha256(text).hexdigest()[:16],
    )


def grenze_aus_flurstuecken(flurstuecke: Flurstuecke, kennzeichen: list[str]) -> tuple[dict, float]:
    """Bildet die Gartengrenze aus den gewählten Flurstücken.

    Gibt die Fläche als MultiPolygon und die Summe der amtlichen Flächen zurück.
    Unbekannte Kennzeichen lösen einen KeyError aus.
    """
    polygone = []
    flaeche = 0.0
    for k in kennzeichen:
        eintrag = flurstuecke.nach_kennzeichen[k]
        polygone.extend(eintrag["geometry"]["coordinates"])
        flaeche += eintrag["properties"]["m2"]
    return {"type": "MultiPolygon", "coordinates": polygone}, flaeche


def umriss(grenze: dict) -> list:
    """Außenlinie der Gartengrenze als Liste kurzer Strecken.

    Kanten, an denen zwei gewählte Flurstücke aneinanderstoßen, kommen doppelt
    vor und fallen weg. Übrig bleibt der Rand des ganzen Gartens.
    """
    zaehler: dict = {}
    for polygon in grenze["coordinates"]:
        for ring in polygon:
            for a, b in zip(ring, ring[1:]):
                kante = (tuple(a), tuple(b))
                schluessel = kante if kante[0] <= kante[1] else (kante[1], kante[0])
                zaehler[schluessel] = zaehler.get(schluessel, 0) + 1
    return [[list(a), list(b)] for (a, b), anzahl in zaehler.items() if anzahl == 1]


def kachel_rahmen(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Ausdehnung einer Kartenkachel in Web-Mercator-Metern (EPSG:3857)."""
    breite = 2 * ERDHALB / (2**z)
    west = -ERDHALB + x * breite
    nord = ERDHALB - y * breite
    return west, nord - breite, west + breite, nord


def kachel_fuer(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return x, y


def kachel_im_gebiet(rahmen: tuple, z: int, x: int, y: int, rand: float = 0.3) -> bool:
    """Liegt die Kachel im Gebiet der Flurstücke? Der Rand deckt ab, was die Karte am Handy zeigen kann."""
    west, sued, ost, nord = rahmen
    dx, dy = (ost - west) * rand, (nord - sued) * rand
    x_min, y_min = kachel_fuer(west - dx, nord + dy, z)
    x_max, y_max = kachel_fuer(ost + dx, sued - dy, z)
    return x_min - 1 <= x <= x_max + 1 and y_min - 1 <= y <= y_max + 1
