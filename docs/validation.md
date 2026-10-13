# Ausgeführte Abnahme

Stand: 13. Oktober 2026, Windows 11 / RTX 4070 / i7-11700F. Private Rohberichte liegen im installierten Datenordner unter `benchmarks/`; sie werden nicht mit der Website veröffentlicht.

## Reale lokale Funktionen

Der HTTP-End-to-End-Test bestand Registrierung auf der Backend-Origin, Recovery-Code-Anzeige, PKCE/S256 mit exakter Rückkehradresse und einmaligem Code, ausschließlich cookiegebundene Refresh-Credentials, echte gestreamte Qwen-Antwort, KI-Profilerstellung, gespeicherte Nachrichten/Erinnerungen, Piper-Audio als gültige WAV-Datei, Datenexport und anschließende Löschung des eigenen Testkontos. Ein früheres durch einen Fehler im Testhelfer zurückgebliebenes Testkonto wurde gezielt entfernt; andere Konten wurden nicht angefasst.

Bei einer kurzen warmen deutschen Antwort kamen 18 Stream-Fragmente in 0,61 Sekunden an. Die deutsche KI-Profilerstellung benötigte 5,94 Sekunden, der Piper-Auftrag über die API 1,44 Sekunden. Diese einzelnen kurzen Beispiele sind keine allgemeinen Latenzgarantien.

Getrennte reale Sprachtests bestanden für Piper Thorsten/Kerstin, englisches Kokoro mit männlicher und weiblicher Stimme sowie XTTS auf CPU. Kokoro verwendete bei drei warmen Aufträgen denselben Prozess und benötigte etwa 1,4–1,6 Sekunden; der untersuchte XTTS-Auftrag einschließlich Initialisierung benötigte etwa 41 Sekunden. Fehlende Modelle werden nicht durch erfundene Antworten ersetzt.

Reale Qwen-Prüfungen liefen auf einem harmlosen fiktiven Erwachsenenprofil in Deutsch und auf einem englischen Profil mit einem eigens erzeugten abstrakten Testavatar. Beide ergaben eine strukturierte Freigabeentscheidung. Der Vision-Projektor wurde tatsächlich auf CPU geladen. Das ist ein Integrationstest; eine ausreichende Inhaltskalibrierung mit Foto-/Anime- und schwierigen DE-/EN-Beispielen steht weiterhin aus.

## GPU-Modellwechsel

Der explizite private Test bestand **20 tatsächliche Wechsel** zwischen Chat und Qwen Image: 21 Lade- und 21 Entladevorgänge, insgesamt 446,36 Sekunden, kein beobachteter OOM. Bilder verwendeten 512 × 512 Pixel und einen Sampling-Schritt.

Der globale VRAM-Ausgangswert lag bei 1.068 MiB, der abschließende Wert bei 1.119 MiB. Die Werte nach dem Entladen lagen zwischen 1.057 und 1.137 MiB; es wurde kein materiell stetiger Anstieg festgestellt. Der höchste abgetastete globale VRAM-Wert war 11.625 von 12.282 MiB. Mindestens etwa 12,4 GiB System-RAM blieben frei. Eine Vorabprüfung misst freien GPU-Speicher und meldet fremde GPU-Prozesse; sie beendet sie nicht.

Der Test bestätigt Prozesswechsel und Freigabe auf dieser Hardware. Er bestätigt keine harte Speicherobergrenze während transienter Modelloperationen und keine Bildqualität oder maximale Kapazität bei 1 MP, Referenzbildern oder 15/25 Schritten.

## Echter Chat-Scheduler

Vier Teststufen verwendeten jeweils getrennte Konten, eigene Charaktere und Gespräche in einer isolierten Datenbank. Alle Aufträge verwendeten echtes Qwen und maximal 64 Ausgabetokens. Jeweils höchstens ein GPU-Auftrag lief, und jede gespeicherte Antwort gehörte zum richtigen Konto und Gespräch.

| Konten / Aufträge | Gesamtdauer | Median bis erstem Token einschließlich Queue | Größte gemessene Wartezeit |
| ---: | ---: | ---: | ---: |
| 2 | 2,56 s | 0,90 s | 1,34 s |
| 5 | 5,70 s | 2,17 s | 4,31 s |
| 10 | 11,03 s | 4,73 s | 9,70 s |
| 20 | 22,22 s | 9,69 s | 20,58 s |

Der Median der aus Stream-Zeitstempeln und dem echten Modelltokenizer abgeleiteten Ausgaberate lag bei etwa 59–62 Tokens/s. Die abgetastete globale VRAM-Spitze lag bei etwa 6,4 GiB. Diese Messung beschreibt kurze serielle Chat-Aufträge im Scheduler; sie ist keine Zusage für zwanzig gleichzeitig dauerhaft aktive Websitebesucher oder gemischte Bild-/Sprachlast.

## Automatische und betriebliche Prüfungen

Backend-, Provider-, Launcher- und Frontendtests prüfen Eigentumsschutz, Quotenpersistenz, Abbruch, SSE-Replay/Widerruf, Moderationsausfälle, sichere Uploads, Gesprächszweige, Quelleninvalidierung, Backups und Wiederherstellung. Native Windows-Tests bestätigten die Beendigung zugeordneter Kinder und Enkel durch Schließen des Job Objects. Der reale Supervisor ließ nach `offline.bat` keine eigenen API-/Admin-/Chat-/Control-Listener zurück. Die Verwaltung lieferte anonym 403 und erschien auf der öffentlichen API als 404.

Ein echtes konsistentes SQLite-/Medienbackup wurde erstellt und anschließend anhand seines Manifests geprüft. Wiederherstellung in einen getrennten Datenordner, Sitzungswiderruf und die Ablehnung einer Wiederherstellung in ein laufendes Backend sind automatisiert geprüft.

TypeScript-Prüfung, Frontendtests, Produktionsbuild und npm-Audit bestanden. Die OpenAPI-Typen werden reproduzierbar generiert. GitHub Actions wiederholt die Backendtests auf Windows und Linux; nur der statische Frontend-Build wird an Pages übergeben.

## Ausstehende externe und manuelle Abnahme

Tailscale ist installiert und angemeldet; die feste Adresse ist lokal und als GitHub-Variable konfiguriert. Die einmalige Funnel-/HTTPS-Kontofreigabe, Begrenzung der Funnel-Berechtigung auf den Betreiber und Abschaltung des Geräteschlüsselablaufs müssen in der Tailscale-Verwaltung abgeschlossen sein. Öffentlicher Healthcheck, öffentlicher Kontenablauf, Stop/Start über dieselbe Adresse und Funnel-Durchsatz werden erst danach als bestanden vermerkt.

Die automatische Browserprüfung der lokalen Oberfläche wurde durch die Browser-Sicherheitsprüfung mit der Meldung eines unzulässigen URL-Protokolls abgelehnt. Es wurde keine alternative Browsertechnik zur Umgehung verwendet. JSDOM-/HTTP-/Vertragstests bestehen; visuelle Prüfung bei 360 px, tatsächlich gesperrte Drittanbieter-Cookies, Smartphone über Mobilfunk, Fenster-X, Hardkill und Windows-Neustart bleiben gesonderte manuelle Abnahmepunkte.

Die öffentliche Qwen-Bildfunktion bleibt bis zur dokumentierten Nutzungserlaubnis gesperrt. Es wird keine pauschale Modell-/Stimmlizenzfreigabe oder garantierte Verfügbarkeit zugesagt; konkrete Nachweise stehen im Modellmanifest und in den Drittanbieterhinweisen.
