"""Lexikon typischer Pflanzen und die Vorlagen für Pflegeanleitungen.

Beides liegt als Datei im Repo. Das Lexikon wird nur gelesen. Die Anleitungen
werden beim Start in die Datenbank übernommen, damit der Meister sie dort
ändern kann. Was er geändert hat, bleibt bei einem Update erhalten.
"""

import calendar
import json
from datetime import date, timedelta
from functools import lru_cache

from . import PROJEKT

MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember"]


@lru_cache(maxsize=1)
def lade_lexikon() -> dict:
    roh = json.loads((PROJEKT / "data" / "lexikon.json").read_text(encoding="utf-8"))
    return {e["id"]: e for e in sorted(roh, key=lambda e: e["name"].lower())}


def saee_anleitungen(con) -> None:
    """Legt Vorlagen an, die es in der Datenbank noch nicht gibt."""
    vorlagen = json.loads((PROJEKT / "data" / "anleitungen.json").read_text(encoding="utf-8"))
    vorhanden = {z[0] for z in con.execute("SELECT schluessel FROM anleitungen WHERE schluessel IS NOT NULL")}
    for v in vorlagen:
        if v["schluessel"] in vorhanden:
            continue
        con.execute(
            "INSERT INTO anleitungen (schluessel, titel, schritte, werkzeug, sicherheit, monat_von, monat_bis,"
            " intervall_monate) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (v["schluessel"], v["titel"], "\n".join(v["schritte"]), v["werkzeug"], v["sicherheit"], v["monat_von"],
             v["monat_bis"], v["intervall_monate"]),
        )
    con.commit()


def zeitraum(monat_von, monat_bis) -> str:
    """„Februar bis März“ oder „Juni“."""
    if not monat_von:
        return ""
    if not monat_bis or monat_bis == monat_von:
        return MONATE[monat_von - 1]
    return f"{MONATE[monat_von - 1]} bis {MONATE[monat_bis - 1]}"


def im_zeitraum(monat: int, monat_von: int, monat_bis: int) -> bool:
    if monat_von <= monat_bis:
        return monat_von <= monat <= monat_bis
    return monat >= monat_von or monat <= monat_bis  # über den Jahreswechsel


def erster_termin(monat_von, monat_bis, heute: date) -> date:
    """Wann eine neue Aufgabe das erste Mal fällig ist.

    Läuft der passende Zeitraum gerade, ist sie in einer Woche fällig. Sonst am
    ersten Tag des nächsten Zeitraums. Ohne Zeitraum in einem Monat.
    """
    if not monat_von:
        return heute + timedelta(days=30)
    if im_zeitraum(heute.month, monat_von, monat_bis or monat_von):
        return heute + timedelta(days=7)
    jahr = heute.year if monat_von > heute.month else heute.year + 1
    return date(jahr, monat_von, 1)


def plus_monate(tag: date, monate: int) -> date:
    monat = tag.month - 1 + monate
    jahr = tag.year + monat // 12
    monat = monat % 12 + 1
    return date(jahr, monat, min(tag.day, calendar.monthrange(jahr, monat)[1]))
