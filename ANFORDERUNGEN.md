# Garten-Kartierung – Anforderungen

Stand: 9.11.2026. Nur Anforderungen, keine technische Umsetzung. Offene Punkte stehen am Ende.

## Ziel

Gärten kartieren und die Pflege über Jahre mit einem Fachmann zusammen planen.
Die Pflege soll sich am aktuellen Zustand orientieren: Der Zustand bestimmt, was zuerst gemacht werden muss.

## Rollen

- **Besitzer / Lehrling:** Sven. Gehört der Garten, führt die Pflege aus und dokumentiert.
- **Meister / Mentor:** Johannes. Plant, gibt Anleitungen und setzt Prioritäten.
- Beide Rollen sind einem Garten zugewiesen. Beide müssen von unterwegs arbeiten können.
- Weitere Nutzer sind nicht geplant.

## Gärten und Grundstück

- Garten anlegen mit Name und Adresse.
- Grundstück auf der Karte über **Flurstücke** auswählen. Die Flurstücke gibt es nur für **Feggendorf**.
- Die gewählten Flurstücke markieren die Grenze des Gartens. Die Grenze bleibt sichtbar.
- Gartenfläche zusätzlich zeichnen können, wenn das Flurstück nicht passt.
- **Kartenansicht pro Garten gespeichert:** Beim Öffnen eines Gartens zeigt die Karte immer dessen Grenzen und den gespeicherten Zoom. Man muss nicht suchen.

## Kartierung

- **Pflanzen** und **Objekte** (Weg, Teich, Zaun, Terrasse, Gebäude usw.) auf der Karte setzen oder zeichnen.
- Jeder Eintrag hat Name, Kategorie, Standort-Notiz und einen Zustand von 1 (kritisch) bis 5 (sehr gut).
- Auswahl aus einem **Lexikon typischer Pflanzen für Feggendorf**. Eine Pflanze aus dem Lexikon übernimmt Standardwerte und passende Pflegeaufgaben.
- Lexikon-Angaben sind Richtwerte und werden als solche gekennzeichnet.

## Wissen

- Zu jeder Pflanze und jedem Objekt Wissen speichern: Titel, Text, Kategorie (z. B. Pflege, Standort, Krankheit, Sorte).
- Bilder und Videos hinzufügen (Bilder bis 10 MB, Videos bis 200 MB).
- Vorher/Nachher-Fotos einer Maßnahme zuordnen können.

## Pflegehistorie

- Protokoll: was wurde wann gemacht (Schnitt, Düngen, Gießen, Pflanzen usw.) und welcher Zustand danach.
- **Watch-Kalender:** Beobachtungen wie Knospe, Austrieb, Blüte, Fruchtansatz, Laubfall mit Datum. Jahre sollen vergleichbar sein.
- Zustandsverlauf pro Pflanze sichtbar machen.

## Planung und Prioritäten

- Pflegeaufgaben an einem Objekt anlegen, mit Fälligkeit und optionalem Intervall (z. B. alle 12 Monate).
- Jede Aufgabe hat eine **Anleitung** (Schritte, Werkzeug, Sicherheit). Der Meister pflegt die Anleitungen.
- Prioritäten werden aus dem **aktuellen Zustand** abgeleitet (z. B. schlechter Zustand, überfällig, passende Saison).
- Der Meister kann die Priorität auch von Hand festlegen.
- Erledigte Aufgabe: Protokoll schreiben, neuer Zustand, Folgetermin bei Intervall.
- Die Startseite zeigt die Aufgaben nach Priorität.

## Termine

- Kalender-Export (ICS) für Pflegetermine.
- Jeder Termin mit zwei Erinnerungen: 1 Tag vorher und 1 Stunde vorher.

## GPS und Vermessung

- Am Handy den eigenen Standort anzeigen und Pflanzen an dieser Stelle setzen.
- Punkte einmessen und Abstände zwischen zwei Punkten messen.
- Gartenbegrenzung abgehen und als Fläche speichern (Fläche und Umfang).
- Hinweis in der App: Das ist eine Orientierungsmessung, keine amtliche Vermessung.
- GPS im Browser braucht HTTPS. Die App muss deshalb über einen Tunnel erreichbar sein.

## Technik und Betrieb

- Läuft auf dem Raspberry Pi zu Hause. Im LAN erreichbar, zusätzlich über Tunnel.
- Mobile-first: Bedienung auf dem Handy muss einfach sein.
- Intuitiv bedienbar, aber mit Struktur, in der sich jeder zurechtfindet.
- Die Oberfläche soll hochwertig und durchdacht wirken, nicht wie ein Prototyp.

## Offene Punkte

1. Welche Flurstücke genau zum Garten gehören: Zuerst nur die Auswahl, oder auch Wunsch, dass der Garten automatisch aus der Flurstück-Auswahl gebildet wird?
2. Soll die Karte ein Luftbild zeigen? (Nur zur Anzeige, nicht zur Vermessung.)
3. Wie viele Gärten sind geplant? (Im Moment: einer.)
4. Soll Wetter oder ein Gießplan dazukommen, oder ist das später?
5. Passwörter und Tunnel-Adresse: Wie soll der Zugang gesichert sein? (Im Moment: Anmeldung per Benutzername und Passwort.)
