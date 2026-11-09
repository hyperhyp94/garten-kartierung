"""Reine Hilfsfunktionen: Prioritäten, Datumsrechnung, iCalendar-Export."""
from __future__ import annotations

import calendar
import datetime as dt


def add_months(d: dt.date, n: int) -> dt.date:
    """Addiert n Monate zu einem Datum (Tag wird bei Bedarf gekürzt)."""
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return dt.date(y, m, day)


def parse_saison(s) -> set[int]:
    """'1,2,3' -> {1, 2, 3}. Ungültige Einträge werden ignoriert."""
    out = set()
    for part in str(s or "").replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit() and 1 <= int(part) <= 12:
            out.add(int(part))
    return out


def berechne_prioritaet(faellig_am, heute, zustand=3, saison="", prio_manuell=None) -> int:
    """Gibt Priorität 1 (hoch), 2 (mittel) oder 3 (niedrig) zurück.

    Punkte:
      - Überfälligkeit: >14 Tage +3, >0 Tage +2, bis 7 Tage vor Fälligkeit +1
      - Zustand des Objekts: 1–2 +2, 3 +1
      - Saison: heute im Saisonfenster +1
    Ab 4 Punkten Prio 1, ab 2 Punkten Prio 2, sonst Prio 3.
    Eine manuelle Prio (1–3) überschreibt die Automatik.
    """
    if prio_manuell in (1, 2, 3, "1", "2", "3"):
        return int(prio_manuell)
    score = 0
    if faellig_am is not None:
        tage = (heute - faellig_am).days
        if tage > 14:
            score += 3
        elif tage > 0:
            score += 2
        elif tage >= -7:
            score += 1
    z = zustand if zustand is not None else 3
    if z <= 2:
        score += 2
    elif z == 3:
        score += 1
    months = parse_saison(saison)
    if months and heute.month in months:
        score += 1
    if score >= 4:
        return 1
    if score >= 2:
        return 2
    return 3


def _ics_escape(text: str) -> str:
    return (str(text or "").replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n"))


def ics_kalender(termine, name="Garten-Kalender", uhrzeit=(9, 0)) -> str:
    """Erzeugt ein iCalendar-Dokument.

    termine: Liste von dicts mit uid, titel, datum (dt.date), beschreibung.
    Jeder Termin bekommt ZWEI Erinnerungen: 1 Tag vorher und 1 Stunde vorher.
    Die Zeiten sind 'floating' (lokale Zeit des Geräts, z. B. Europe/Berlin).
    """
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Garten-Kartierung//DE",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_ics_escape(name)}",
    ]
    h, m = uhrzeit
    for t in termine:
        start = dt.datetime.combine(t["datum"], dt.time(h, m))
        end = start + dt.timedelta(hours=1)
        lines += [
            "BEGIN:VEVENT",
            f"UID:{t['uid']}@garten-kartierung",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{_ics_escape(t['titel'])}",
            f"DESCRIPTION:{_ics_escape(t.get('beschreibung', ''))}",
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            "DESCRIPTION:Morgen fällig",
            "TRIGGER:-P1D",
            "END:VALARM",
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            "DESCRIPTION:In einer Stunde fällig",
            "TRIGGER:-PT1H",
            "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
