# Garten-Kartierung · Plan

Stand 10.11.2026. Grundlage ist `ANFORDERUNGEN.md`. Dieser Plan legt fest, was gebaut wird, in welcher Reihenfolge und was bewusst wegbleibt.

## Grundsatz

Die App wird am Handy im Garten benutzt. Daraus folgen vier Regeln, an denen jede Seite gemessen wird.

1. Jede häufige Aktion braucht höchstens drei Tipper.
2. Alles Wichtige liegt im unteren Drittel des Bildschirms und ist mit dem Daumen erreichbar.
3. Zuerst das Foto, dann der Text. Tippen ist die Ausnahme.
4. Eine Eingabe geht nie verloren, auch wenn das Netz gerade weg ist.

## Aufbau

Vier Bereiche in der unteren Leiste, dazu ein großer Plus-Knopf.

| Bereich | Was man dort sieht |
|---|---|
| Heute | Aufgaben nach Dringlichkeit, als Karten mit Foto der Pflanze, Ampel und Begründung |
| Karte | Luftbild mit Gartengrenze, Pflanzen und Objekte als Symbole in der Farbe ihres Zustands |
| Bestand | Alle Pflanzen und Objekte als Liste mit Suche, sortierbar nach Zustand |
| Mehr | Lexikon, Anleitungen, Kalender-Export, Vermessung, Einstellungen |

Der Plus-Knopf bietet überall dasselbe an, nämlich Foto, Beobachtung, Maßnahme, Frage an Johannes und neue Pflanze.

Solange es nur einen Garten gibt, öffnet die App direkt diesen Garten. Eine Gartenauswahl erscheint erst ab dem zweiten.

## Die Abläufe, die sitzen müssen

**Aufgabe erledigen.** Aufgabe antippen, Anleitung lesen, „Erledigt“ tippen, Foto machen, Zustand über fünf große Felder wählen. Der Folgetermin entsteht von selbst.

**Pflanze erfassen.** Plus, Foto, Art aus dem Lexikon wählen, Karte unter das Fadenkreuz schieben, Zustand wählen. Name und passende Pflegeaufgaben kommen aus dem Lexikon und lassen sich danach ändern.

**Beobachtung festhalten.** Plus, Pflanze wählen, Phase antippen (Knospe, Austrieb, Blüte, Fruchtansatz, Laubfall), Foto.

**Rundgang.** Einmal im Monat führt die App Pflanze für Pflanze durch den Garten. Pro Pflanze ein Foto und ein Tipper für den Zustand. So bleibt der Zustand aktuell, und davon hängt die ganze Planung ab.

**Frage an Johannes.** Sven macht ein Foto und schreibt eine Frage dazu. Johannes zeichnet die Antwort direkt ins Bild und schreibt einen Satz. Frage und Antwort bleiben an der Pflanze hängen.

## Entscheidungen

Die offenen Punkte aus den Anforderungen sind hier mit einem Vorschlag beantwortet. Widerspruch ist jederzeit möglich, nichts davon ist teuer zu ändern.

| Thema | Entscheidung |
|---|---|
| Gartengrenze | Sie entsteht automatisch aus den angetippten Flurstücken. Eine eigene Fläche zeichnen kommt in Stufe 5. |
| Karte | Luftbild als Standard, Straßenkarte zum Umschalten. Das offene Luftbild des Landes Niedersachsen ist geprüft und passt (20 cm pro Bildpunkt, frei nutzbar mit Quellenangabe). Der Pi speichert jede Kachel zwischen, damit die Karte schnell bleibt. Fällt das Luftbild aus, zeigt die App von selbst die Straßenkarte. |
| Position einer Pflanze | Per Fadenkreuz auf der Karte. Das Handy-GPS liegt 3 bis 10 Meter daneben und zeigt deshalb nur grob den eigenen Standort. |
| Anzahl Gärten | Einer. Das Datenmodell kann mehrere, die Oberfläche zeigt das erst bei Bedarf. |
| Zugang | Benutzername und Passwort für Sven und Johannes, Sperre nach mehreren Fehlversuchen, von außen über den HTTPS-Tunnel. |
| Rollen | Beide dürfen alles erfassen. Nur Johannes ändert Anleitungen und legt eine Priorität von Hand fest. |
| Ohne Netz | Kein vollständiger Offline-Betrieb. Stattdessen bleibt jede Eingabe samt Foto auf dem Handy gespeichert, bis sie wirklich gesendet ist. Die App sendet sie von selbst nach, sobald wieder Netz da ist, und legt dabei nie einen Eintrag doppelt an. |
| Wetter | Kommt nach Stufe 5, siehe „Später“. |
| Handys | Ein Android-Gerät und ein iPhone. Jede Stufe wird in beiden Browsern geprüft (Chrome und Safari). Das iPhone braucht mindestens iOS 15.4 aus dem Jahr 2022. |

## Dringlichkeit

Die Regel ist absichtlich einfach, damit jeder nachvollziehen kann, warum eine Aufgabe oben steht.

| Stufe | Wann |
|---|---|
| Jetzt | Heute fällig oder überfällig, oder fällig in den nächsten 14 Tagen bei Zustand 1 oder 2, oder von Johannes so festgelegt |
| Bald | Fällig in den nächsten 30 Tagen |
| Später | Alles andere |

Innerhalb einer Stufe steht die Pflanze mit dem schlechtesten Zustand oben. Jede Aufgabe zeigt ihren Grund im Klartext, zum Beispiel „überfällig seit 12 Tagen, Zustand 2“. Die Saison steckt im Fälligkeitsdatum, das die Vorlage aus dem Lexikon passend setzt.

## Daten

Sieben Tabellen statt elf wie im ersten Versuch. Der wichtigste Unterschied ist, dass alles, was an einer Pflanze passiert, ein Eintrag im selben Verlauf ist.

| Tabelle | Inhalt |
|---|---|
| Nutzer | Sven und Johannes mit Rolle |
| Gärten | Name, Adresse, Flurstücke, Grenze, gespeicherte Kartenansicht |
| Bestand | Pflanzen und Objekte mit Kategorie, Position, aktuellem Zustand und Verweis ins Lexikon |
| Einträge | Maßnahme, Beobachtung, Wissen, Frage, Antwort oder Zustandsänderung, jeweils mit Datum, Text und optional neuem Zustand |
| Medien | Bilder und Videos zu einem Eintrag, mit Kennzeichen vorher oder nachher |
| Aufgaben | Titel, Fälligkeit, Intervall, Anleitung, feste Priorität |
| Anleitungen | Vorlagen mit Schritten, Werkzeug und Sicherheit, gepflegt von Johannes |

Das Lexikon und die Flurstücke bleiben Dateien im Repo. Lexikon-Angaben sind in der App als Richtwert gekennzeichnet.

## Technik

So wenig wie möglich, damit es auf dem Raspberry Pi einfach läuft und sich leicht warten lässt.

1. Python mit Flask und SQLite, Start über einen einzigen Dienst auf dem Pi.
2. Seiten kommen fertig vom Server, dazu wenig eigenes JavaScript. Kein Build-Schritt, kein Node auf dem Pi.
3. Leaflet für die Karte, lokal mitgeliefert.
4. Die App lässt sich auf dem Startbildschirm installieren und startet dann ohne Browserleiste.
5. Fotos werden schon auf dem Handy verkleinert, damit der Upload über Mobilfunk Sekunden dauert. Dabei werden sie in JPEG umgewandelt, sodass das Fotoformat des iPhones (HEIC) auf dem Pi keine Rolle spielt. Bilder bis 10 MB, Videos bis 200 MB, Videos werden unverändert gespeichert.
6. Automatische Tests für Anmeldung und Rechte, Dringlichkeit, Folgetermin, Upload und Kalender-Export.
7. Tägliche Sicherung der Datenbank und der Uploads auf dem Pi.

## Reihenfolge

Stand 10.11.2026: Alle fünf Stufen sind umgesetzt und automatisch getestet. Der Test auf den echten Handys im Garten steht noch aus.

Nach jeder Stufe ist die App am Handy benutzbar und wird im Garten ausprobiert, bevor die nächste beginnt.

| Stufe | Inhalt | Fertig, wenn |
|---|---|---|
| 1 Fundament | Anmeldung, Garten anlegen, Flurstück antippen, Luftbild, gespeicherte Kartenansicht, Installation auf dem Startbildschirm | Beide öffnen die App am Handy und sehen sofort den Garten mit Grenze |
| 2 Bestand | Pflanzen und Objekte erfassen mit Fadenkreuz und Foto, Lexikon, Liste mit Suche, Detailseite mit Verlauf, Wissen und Bildern | Eine Pflanze ist in unter einer Minute erfasst |
| 3 Pflege | Aufgaben und Anleitungen, Dringlichkeit, Seite „Heute“, Erledigen mit Vorher und Nachher, Folgetermin, Rundgang | Sven arbeitet einen Samstag nur mit der Seite „Heute“ |
| 4 Zusammenarbeit | Frage am Foto mit Zeichnen im Bild, Beobachtungen mit Jahresvergleich, Zustandsverlauf, Kalender-Export mit zwei Erinnerungen | Eine Frage ist ohne WhatsApp gestellt und beantwortet |
| 5 Vermessung | Eigener Standort, Abstand messen, Flächen und Linien zeichnen (Beet, Weg, Zaun, eigene Gartenfläche), Grenze abgehen mit Fläche und Umfang, Hinweis auf Orientierungsmessung | Ein Beet ist als Fläche auf der Karte |

## Später

Diese Ideen sind gut, kommen aber erst, wenn die fünf Stufen im Alltag funktionieren.

1. Fotoschablone, bei der das letzte Bild halb durchsichtig über der Kamera liegt, für Zeitraffer über Jahre
2. Wetter vom Deutschen Wetterdienst mit Frostwarnung und Gießhinweis
3. Mehrjahresplan pro Pflanze, etwa ein Verjüngungsschnitt über drei Winter
4. Lernstand des Lehrlings pro Arbeit
5. Schilder mit QR-Code an den Pflanzen
6. Sprachnotiz statt Tippen
7. Materialliste aus den anstehenden Aufgaben
8. Gartenbuch zum Jahresende als PDF
9. Vollständiger Betrieb ohne Netz

## Was nicht gebaut wird

Keine amtliche Vermessung, keine Flurstücke außerhalb von Feggendorf, keine Registrierung weiterer Nutzer, keine Cloud.

## Offen

1. Unter welcher festen Adresse soll der Tunnel erreichbar sein? Ein Tunnel lässt sich öffnen, für die App auf dem Startbildschirm muss die Adresse aber gleich bleiben.
2. Reicht das WLAN bis in den Garten, oder läuft dort alles über Mobilfunk?
