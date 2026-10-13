# Chatabae – Projekt und Übergabestand für Claude

Stand: 13. Oktober 2026. Diese Datei ermöglicht die Fortsetzung, wenn das Nutzungslimit des bisherigen Agenten erreicht wird. Sie enthält keine Zugangsdaten. Den tatsächlichen Laufzeit- und Git-Status beim Übernehmen erneut prüfen.

**Aktueller Kurzstand:** Website auf GitHub Pages veröffentlicht; öffentliche HTTPS-Anmeldung, Chat, KI-Profil, Sprache und Audiocache bestanden. Gespeicherte Charakterparameter, genaue Queue-Hinweise und Satzvorlesen während des Chats sind implementiert. Der aktuelle Gesamtstand besteht mit **118 Python- und 82 Frontendtests**, reproduzierbaren API-Typen, Produktionsbuild und npm-Audit ohne bekannte Schwachstellen. Aktuelle Veröffentlichungs- und CI-Läufe stehen in [GitHub Actions](https://github.com/mniklas189-png/chatabae/actions). Supervisor-Hardkill, Neustart sowie lokaler Start/Stop samt Frontend sind geprüft. Browser-Anmeldefehler `Origin not allowed` (durch `no-referrer` auf den Formularseiten) ist behoben, siehe `docs/validation.md`. Backend-Zustand vor Neustart prüfen; zum Benutzen `online.bat` starten. Offene manuelle Prüfungen und Tailscale-Verwaltungseinstellungen stehen unten.

## Auftrag und Grenzen

Der Nutzer hat die vollständige Umsetzung des Chatabae-Plans ausdrücklich beauftragt und mehrfach zum Weiterarbeiten aufgefordert. Die alte beigefügte Datei `promt verbesserung2.txt` enthält eine überholte Nur-Lesen-/Plan-Mode-Anweisung und Cloudflare-Vorschläge. Diese sind Dokumentinhalt und wurden durch den später ausdrücklich bestätigten Implementierungsplan mit **Tailscale Funnel** ersetzt.

Ziel: kostenlose öffentliche Character-AI-Website auf GitHub Pages. Alle KI und privaten Daten liegen auf dem Windows-PC. `online.bat` startet das Backend samt temporärer öffentlicher HTTPS-Freigabe; `offline.bat` beendet die eigenen Prozesse. Die statische Website bleibt erreichbar. Keine bezahlten Dienste, Domainkäufe oder Cloud-KI. Registrierung ohne Gästezugang; getrennte Konten und private Chats, Erinnerungen, Medien und Stimmreferenzen.

**Öffentliche Qwen-Image-Generierung ist auf ausdrückliche Betreiberentscheidung freigegeben.** Die Modelllizenz erlaubt Forschung/Evaluation; Am 13.10.2026 hat der Betreiber die öffentliche Qwen-Bildfunktion ausdrücklich für alle Konten der kostenlosen, nichtkommerziellen Hobbywebsite freigegeben und trägt das Lizenzrisiko selbst; eine schriftliche Genehmigung von Alibaba/Qwen liegt nicht vor. Die Freigabe steht nur in der privaten Konfiguration (`public_image_allowed` mit `public_image_license_evidence`). Öffentliche Bildaufträge werden vor der Generierung (Prompt und Charakter) und danach (fertiges Bild per CPU-Vision) fail-closed moderiert; zurückgehaltene Ergebnisse werden gelöscht und nicht gespeichert. XTTS ist für den unbezahlten Hobbybetrieb eingerichtet; erzeugtes Audio muss seine CPML-Lizenz-URL mitliefern.

**Szenenbilder und Erwachsenenmodus (13.10.2026):** Bildaufträge aus einer Unterhaltung lassen zuerst das Chatmodell einen Bildprompt aus Charakterbogen, Zusammenfassung und den letzten zwölf Nachrichten schreiben, damit der Charakter im aktuellen Moment (Ort, Kleidung, Tätigkeit) erscheint; der Bilddialog bietet Vorschläge wie „Wie siehst du aus?“, und Chatnachrichten wie „Schick mir ein Selfie“ lösen ebenfalls ein Bild aus. Auf Wunsch des Betreibers gibt es einen Erwachsenenmodus: Konten können ihn in den Einstellungen nur nach ausdrücklicher 18+-Bestätigung einschalten (`users.adult_confirmed_at`, Migration 0004, `PUT /api/v1/me/adult-content`). Er lockert Chatregeln, Bildprompt und Bildmoderation nur für Charaktere ab 18 Jahren. Unverändert gesperrt bleiben sexuelle Inhalte mit Minderjährigen oder kindlich wirkenden Personen und sexuelle bzw. realistische Darstellungen benannter realer Personen; öffentlich geteilte Charaktere werden weiter nach den Standardregeln moderiert. Eine Checkbox ist keine Altersverifikation im Sinne von JMStV/§184 StGB; dieses Rechtsrisiko trägt der Betreiber. Die Bildmoderation läuft innerhalb der GPU-Lease des Bildjobs auf dem GPU-Chatmodell und rät keine realen Identitäten aus Gesichtern mehr.

**Gruppenchats, KI-Profilbilder und Bildanimation (13.10.2026):** Gruppenchats mit zwei bis vier Charakteren (`POST /api/v1/group-conversations`, `conversations.member_ids`, `messages.character_id`, Migration 0005). Mit Namen angesprochene Charaktere antworten in Nennungsreihenfolge, sonst alle reihum ab dem nächsten Sprecher; jede Antwort wird vor dem nächsten Sprecher gespeichert, Tokens tragen `character_id`, ein `speaker`-Event markiert den Wechsel. Ein Mitglied unter 18 hält die Standardregeln für die ganze Gruppe; Regeneration betrifft nur den Sprecher der Nachricht; Zweige übernehmen Mitglieder und Sprecher; gelöschte Mitglieder werden entfernt, eine Gruppe mit einem verbleibenden Mitglied wird ein normaler Chat. Automatisches Satzvorlesen ist in Gruppen aus, manuelles Vorlesen nutzt die Stimme des Sprechers. Der Editor erzeugt KI-Profilbilder über `POST /api/v1/avatar-jobs` (Vorschau, Übernahme beim Speichern); alle KI-erstellten Charaktere erhalten ein Porträt. Porträts haben ein eigenes Tageskontingent (`limits.avatar_per_day`, Standard 10) und blockieren keine Chatbilder. Laufende Bildaufträge zeigen im Chat eine animierte Karte mit Fortschritt aus den `progress`-Events.

**Profilbild beim Erstellen und Smartphone-Ansicht (13.10.2026):** Der Editor zeigt in allen Erstellungsarten oben ein Profilbild-Feld (Hochladen, KI-Bild, Entfernen); ein hochgeladenes Bild ersetzt bei KI-Erstellung das automatische Porträt (`ProfileRequest.portrait=false`). Smartphone-Abnahme bei 375 px mit lokalem Testserver: Anmeldekarten passen in die Breite, Suchfeld repariert, Eingaben 16 px (kein iOS-Zoom), größere Schrift und Touch-Ziele, Löschen ohne Hover sichtbar, Chat im Vollbild ohne doppelte Kopfzeile, Safe-Area-Abstände.

**Filter, Modellwechsel, Fehlerbehebungen und Profilansicht (13.10.2026):** Auf Wunsch des Betreibers sind alle Inhaltsfilter für 18+-Konten entfernt; unverändert bleiben nur die Sperren für sexuelle Inhalte mit Minderjährigen und sexuelle bzw. realistische Darstellungen benannter realer Personen sowie die 18+-Bestätigung als Schalter. Öffentliche Charaktere werden nur noch aus diesen zwei Gründen zurückgehalten; explizite werden als `adult_content` markiert und nur 18+-Konten gezeigt (Galerie, Profil, Gespräche). Chatmodell gewechselt auf Huihui-Qwen3.5-9B-abliterated (SHA-geprüft); im Test 0/6 Verweigerungen gegenüber 1–2/6 vorher. Das alte Qwen bleibt als Moderationsmodell, weil das neue Modell die Moderationsfragen unzuverlässig beantwortete. Behoben: KI-Profile scheiterten, wenn das Modell Felder als Liste/Objekt lieferte; Favoriten-Herzen zeigten den gespeicherten Zustand nicht; jedes Avatarbild wurde pro Karte und Nachricht erneut geladen (jetzt ein gemeinsamer Cache); Funktionsnamen in den Einstellungen. Karten zeigen Porträts randlos, Profile ein großes Porträt vor unscharfem Hintergrund.

**Admin, Fotos von Charakteren, Schreiben während Bildern (13.10.2026):** `admin_usernames` in der privaten Konfiguration nimmt Konten von allen Konto-Limits und Kontingenten aus (Betreiberkonto eingetragen). Limitmeldungen nennen das Limit und die Restzeit; `limits.image_gap_seconds` ist einstellbar. Charaktere können von sich aus ein Foto schicken: Endet eine Antwort mit `[photo: …]`, wird der Text ohne Tag gespeichert und ein Bildauftrag gestartet (bei Limits still übersprungen). Bildaufträge laufen im Hintergrund mit eigener Fortschrittskarte, Nachrichten können währenddessen gesendet werden; nur ein laufender Chat-Auftrag blockiert. Bei 18+ beschreibt der Bildprompt gewünschte Nacktheit ausdrücklich, und das Referenzporträt dient nur noch für Gesicht und Identität, nicht für Kleidung oder Pose. `POST /internal/portraits` (lokale Verwaltung) erzeugt KI-Porträts für alle Charaktere ohne Profilbild und setzt sie nach Fertigstellung.

**Natürlicher Chatstil und Referenzbilder (13.10.2026):** Schreibregeln (kurz, alltagssprachlich, kaum Ausrufezeichen und Emojis, keine Körper-Erzählprosa) stehen am Ende des Systemprompts; spontane Fotos erst nach mindestens 8 Nachrichten ohne Bild. Bilder mit Referenzporträt scheiterten an ComfyUIs DynamicVRAM (`aimdo memory compile error`, comfy-aimdo 0.5.5); die eigene Chatabae-Instanz startet deshalb mit `--disable-dynamic-vram`. Real geprüft: Referenzbild in 80 s.

## Projekt und Architektur

- Arbeitsordner: `C:\Users\meyer\Desktop\!CODING\chatabae`.
- Repository: https://github.com/mniklas189-png/chatabae – öffentlich, `origin`, Branch `main`.
- Website: https://mniklas189-png.github.io/chatabae/.
- Feste API: https://niklas-pc.taila668dd.ts.net.
- React/TypeScript/Vite mit Hash-Routing, Produktionsbase `/chatabae/`; SSE über authentifiziertes `fetch`.
- FastAPI, Pydantic, SQLAlchemy, Alembic, SQLite/WAL und eigentümergeschützte Medien.
- API `127.0.0.1:7810`, getrennte lokale Verwaltung `7811`, Chatmodell `7812`, eigene ComfyUI `7820`, authentifizierter lokaler Stop-Kanal `7813`.
- `launcher/` verwendet Windows Job Objects mit `KILL_ON_JOB_CLOSE`, einschließlich aller Modellkinder und der Foreground-Funnel-CLI. Kein `--bg`, kein globales Funnel-Reset, keine pauschalen Prozesskills.
- `backend/openapi.json` ist die Vertragsquelle für `frontend/src/generated/api-schema.ts`; typisierte `endpoint()`-Methoden verwenden diese Verträge.

## Installation und private Daten

Python 3.12 ist vorhanden. Backend `.venv`, Kokoro `.venv-tts`, XTTS `.venv-xtts` sind installiert. Globales Node 25 wird für dieses Projekt nicht verwendet; portable Node **24.21.0** liegt im privaten Datenordner unter `runtimes/node-v24.21.0-win-x64/node.exe`.

`config/local.json` ist eine **ignorierte Installationsmarkierung**. Sie verweist auf den tatsächlich verwendeten Datenordner. Die Codex-App unter Windows virtualisiert AppData; daher nicht blind einen zweiten `%LOCALAPPDATA%\Chatabae`-Ordner anlegen oder die großen Modelle erneut herunterladen. Der bisherige tatsächliche Ordner lautet:

`C:\Users\meyer\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\Chatabae`

Dort liegen `config.json`, Datenbank, Medien, lokale Geheimnisse, Logs, Backups, Modelle und Benchmarkberichte. Konfiguration und Secrets niemals in Git oder Pages übernehmen. Die Start-/Setup-/Backup-Helfer verwenden die Markierung auch beim späteren Start außerhalb der paketierten App.

Qwen3.5-9B Q4_K_M, CPU-Vision-Projektor und gepinnte llama.cpp-CUDA-Laufzeit sind bereits vollständig installiert und geprüft. Kokoro-Gewichte werden aus einem vorhandenen fixierten Hugging-Face-Snapshot wiederverwendet. Piper Thorsten wird aus dem Nachbarprojekt `!local-ally-code` gelesen; Kerstin und XTTS wurden separat installiert. Modellrevisionen, Prüfsummen und Lizenzketten stehen in `docs/model-manifest.md`, `THIRD_PARTY_NOTICES.md` und den Setup-Helfern.

Die originale `LocalImageAI`-Installation und ihre rund 17,3 GB Bildgewichte werden **nicht verändert oder dupliziert**. Chatabae startet nur eine eigene ComfyUI-Instanz mit eigenen Laufzeit-/Input-/Output-Verzeichnissen.

## Implementierter Funktionsstand

- Backend-HTTPS-Anmeldeformulare, Argon2id, einmalige Recovery-Codes, PKCE/S256, exakter Callback, 60-Sekunden-Code, 15-Minuten-Access-Token im Browser-RAM, cookiegebundene rotierende Refresh-Sitzungen und First-Party-Fallback.
- Eigentumsschutz für Chats, Jobs, Medien und Erinnerungen; geschützte lokale Verwaltung, Kontosperren, Meldungen, Drain, Backup, Hardware-/Sitzungsstatus.
- Manuelle, KI-gestützte und automatische Charaktere, einzelne KI-Feldverbesserungen, editierbare Profilfelder, gespeicherte Generierungsparameter, private Stimmreferenzen und öffentliche geprüfte Snapshots. Temperatur, `top_p` und Antwortlänge sind validiert; Chat und Regeneration verwenden serverseitig die Charakterdefaults, wenn keine eigenen Parameter gesendet werden. Auch reine Parameteränderungen durchlaufen Revision und erneute Veröffentlichungskontrolle.
- Messenger, echter Qwen-Stream, Suche, mehrere Gespräche, Bearbeiten/Regeneration/Zweige, Quelleninvalidierung, Erinnerungen und Zusammenfassungen.
- Typisierte Bildjobs per Button und eindeutigem DE-/EN-Bildkommando, Galerie, Fast15/Balanced25, effektiver Seed und Parameter. Mit Referenzavatar bestimmt die Hauptreferenz das Bildformat; Größenwahl gilt nur ohne Referenz.
- Kokoro/Piper auf CPU, XTTS auf CPU als langsamere Qualitätsoption, Stimmenvorschau, Tempo/Lautstärke, Satzvorlesen während neuer Chatstreams, Pause/Stopp und manuelles Resume bei Autoplayblockade. Die separate Sprachqueue beeinflusst den Chatstream nicht; höchstens zehn Aufträge pro Antwort, begrenzter Textpuffer und keine Quoten-Retryschleife. Wiederhergestellte Streams werden nicht erneut automatisch gesprochen. XTTS beginnt nach der vollständigen Antwort und meldet die Grenze von 1.000 Zeichen, ohne heimlich zu kürzen. Private WAV-Referenzen verlangen Berechtigungsbestätigung; Audiocache und XTTS-Lizenzlink sind implementiert.
- Persistente Quoten, Rundlauf über Konten, eine GPU-Lease, begrenzte CPU-Pools, gemessene VRAM-Prüfung vor Modellladung, verständliche Ressourcenfehler und fremde GPU-Prozesse werden ausschließlich gemeldet. Der öffentliche Queue-Status enthält nur die aktive GPU-Klasse `chat`, `image` oder `null`, ohne Nutzer-, Job- oder Promptdaten.
- Kontoexport/-löschung, tägliche/wöchentliche konsistente Backups, geprüfte Offline-Wiederherstellung, DE/EN, Responsive-CSS und Offline-Beispiele.

## Fortschritt nach Meilenstein

| Meilenstein | Nachgewiesener Stand / verbleibende Abnahme |
| --- | --- |
| 1. Bestand und Voraussetzungen | Laufzeiten und Modelle installiert, Revisionen/Prüfsummen/Lizenzen dokumentiert. |
| 2. Grundgerüst | Frontend, API, Migrationen, Supervisor und getrennte Verwaltung implementiert. |
| 3. Character-Chat | Echter lokaler und öffentlicher Qwen-Stream, Speicherung und Zweige geprüft. |
| 4. Charaktereditor | Drei Erstellungsarten, Erinnerungen, Snapshots und Reports implementiert; schwierige Moderationsbeispiele noch kalibrieren. |
| 5. Bildintegration | Eigene ComfyUI und 20 reale Modellwechsel geprüft; Bildqualität/1-MP-Referenzlast noch prüfen. Öffentliche Nutzung auf Betreiberentscheidung freigegeben, mit Moderation vor und nach der Generierung. |
| 6. Sprache | Reale DE-/EN-Provider und Cache geprüft; Browserwiedergabe bleibt Teil der manuellen Abnahme. |
| 7. Öffentlicher Betrieb | Pages, Funnel, echte HTTPS-Anmeldung und Chat bestanden; zwei Tailscale-Verwaltungseinstellungen noch bestätigen. |
| 8. Ein-Klick-Betrieb | Lokaler/öffentlicher Start, normaler Stop, idle Hardkill und Neustart bestanden; Fenster-X/Windows-Neustart und gemischte aktive Last noch prüfen. |
| 9. Optimierung | Kurze echte Laststufen mit 2/5/10/20 Konten gemessen; gemischte Langzeitlast und Funnel-Durchsatz stehen aus. |
| 10. Fertigstellung | Automatische Prüfungen, Deployment und Backup/Wiederherstellung bestanden; visuelle/mobile Gesamt-Abnahme offen. |

## Nachgewiesene Prüfungen

Der aktuelle Gesamtstand besteht mit **86 Backendtests + 28 Providertests + 4 Launchertests = 118 Python-Tests** sowie **75 Frontendtests**. API-Typen ohne Schema-Drift, TypeScript, Vite-Build und npm-Audit bestanden; Audit meldete null bekannte Schwachstellen. GitHub Actions prüft zusätzlich Windows/Linux und das Frontend.

Neue Frontendregressionen belegen gespeicherte Vorgaben unter Erhalt der Persona, Schutz gegen veraltete GET-Antworten und Kontowechsel, richtige Queue-Hinweise sowie Sprachwiedergabe während offenem Chat-SSE. Stop wartet auch verzögerte Auftragsbestätigungen ab und cancelt die eigene erhaltene ID. Autoplayblockade erlaubt manuelles Resume; Navigation, Autoplay-Aus und Logout erzeugen keine alten XTTS-Aufträge. Wiederhergestellte Sprachjobs sind ebenfalls im Stop-Tracker erfasst. Dies sind JSDOM-/Vertragstests; tatsächliches Browser-Autoplay bleibt ein manueller Abnahmepunkt.

Realer lokaler und öffentlicher HTTPS-Ablauf bestanden: Registrierung/Recovery, PKCE, kein Refresh-Token in JavaScript-JSON, gestreamter Chat, vollständiges KI-Profil, Piper-WAV, tatsächlicher Audiocache, gespeicherte Nachrichten/Erinnerungen, Export und Entfernen des eigenen QA-Kontos. Früher durch Testhelferfehler verwaiste eigene QA-Konten wurden gezielt entfernt; andere Nutzerdaten blieben erhalten. Ein Modell-Formatproblem beim Interessenfeld wurde mit JSON-Schema plus begrenzter Normalisierung von Zeichenkettenlisten behoben und real verifiziert.

**20 echte Chat-/Bildmodellwechsel** bestanden: 446,36 s, 21 Lade-/Entladevorgänge, kein OOM, Ausgangs-VRAM 1.068 MiB, abschließend 1.119 MiB, höchste abgetastete globale Nutzung 11.625 von 12.282 MiB. Der Bildtest verwendete nur 512² und einen Schritt; dies ist kein Nachweis für Bildqualität oder maximale 1-MP-/Referenzkapazität. Die Original-ComfyUI blieb Git-clean; originale LocalImageAI-Logzeiten blieben unverändert.

Echter Chat-Scheduler mit getrennten Testkonten/Charakteren/Gesprächen und maximal 64 Tokens: 2/5/10/20 Aufträge bestanden in 2,56/5,70/11,03/22,22 s. Bei 20 Konten: Median bis erstem Token einschließlich Queue 9,69 s, größte Wartezeit 20,58 s, Median der aus echten Tokens abgeleiteten Ausgaberate etwa 59 Tokens/s. Keine Garantie für zwanzig dauerhaft aktive Websitebesucher.

Echte Textmoderation und Vision-Prüfung mit CPU-Projektor bestanden auf harmlosen künstlichen Testdaten. Umfangreiche Foto-/Anime-/Prompt-Injection-Kalibrierung steht weiterhin aus. Reale Piper-, Kokoro- und XTTS-Sprachsmokes bestanden. Ein reales SQLite-/Medienbackup wurde erstellt und verifiziert; Wiederherstellung ist automatisiert getestet.

## Unmittelbarer Übergabestand

1. Tailscale ist installiert und angemeldet; der Nutzer hat **Funnel bereits aktiviert**. HTTPS-Adresse und GitHub-Variable `VITE_API_BASE_URL` sind konfiguriert. GitHub Pages wurde auf Deployment durch Actions eingestellt.
2. Der öffentliche Supervisor meldete **ONLINE** nach eigenem externen Healthcheck. Normales Stop, gezieltes Hardkill und Neustart funktionierten. Die Foreground-Freigabe und eigene Listener verschwanden beim Hardkill; dieselbe HTTPS-Origin kam mit neuer passender Instanz-ID zurück. Nach der Abnahme wurde das Backend normal gestoppt; die Website bleibt verfügbar. Den tatsächlichen Zustand vor einem Neustart prüfen, keine zweite Instanz erzwingen.
3. Git ist initialisiert, der erste Implementierungsstand ist committed und auf `main` gepusht. GitHub Pages ist veröffentlicht und per HTTP geprüft. Erste **Verify**: https://github.com/mniklas189-png/chatabae/actions/runs/38394547010 (success). Erste **Publish website**: https://github.com/mniklas189-png/chatabae/actions/runs/38394547703 (success). Für die Fortsetzung mit Satzvorlesen/Charakterparametern den aktuellen Commit und die neuesten [Actions-Läufe](https://github.com/mniklas189-png/chatabae/actions) verwenden.
4. HTTP-200-Status mit `online:false` aktiviert die Oberfläche nicht; `connection-lost` wird sofort angezeigt. Nicht verfügbare Modellfunktionen werden vor Jobannahme und Quotenverbrauch mit 503 abgelehnt; fehlende Nutzungsfreigaben behalten Vorrang. Bei Moderationsausfall bleibt die neue Revision zurückgehalten und ein bestehender öffentlicher Snapshot unverändert. Die fortgesetzte Backendprüfung einschließlich Charakterdefaults und Queue-Klassen umfasst 97 erfolgreiche Python-Tests.
5. Migration **0005** ist in der realen lokalen Datenbank angewandt und der Alembic-Stand wurde geprüft. Vor Migrationen entsteht ein Backup. Niemals Nutzerdaten löschen, um Migrationen zu umgehen.
6. Fortsetzung abgeschlossen und lokal gesamtgeprüft: 97 Python-/75 Frontendtests, Build/Audit und API-Typen bestanden. Charakterdefaults haben im Editor eigene Felder; im Messenger speichert ein ausdrücklicher Knopf die Vorgaben des eigenen Charakters. Fremde Charaktere erhalten nur temporäre Einstellungen je Unterhaltung. Satzqueue, Player, verzögerte Auftragsanlage und sämtliche genannten Resume-/Abbruchkorrekturen sind umgesetzt. Vor neuer Arbeit tatsächlichen Git-/CI-/Laufzeitstatus prüfen; übrig bleiben die unten genannten externen/manuellen Abnahmepunkte.

## Fortsetzung und Wiederholungsbefehle

Die folgenden Kernschritte wurden inzwischen ausgeführt und bestanden. Bei Übernahme nur wiederholen, wenn sich Code oder Laufzeitbedingungen ändern; zuerst `docs/validation.md` und den tatsächlichen Git-Status lesen. Vorrang haben jetzt die unten genannten manuellen/externalen Abnahmepunkte und vom Nutzer gewünschte weitere Änderungen.

1. Öffentlichen echten Ablauf ausführen:

```powershell
.\.venv\Scripts\python.exe scripts\check_local.py --allow-online --api https://niklas-pc.taila668dd.ts.net --frontend https://mniklas189-png.github.io/chatabae/
```

Der Helfer erstellt nur sein eigenes zufälliges QA-Konto und löscht es im `finally`. Er darf auf einer fremden oder unkonfigurierten öffentlichen API nicht laufen. Keine Passwörter, Cookies, Tokens oder Auth-Codes ausgeben. Bei Fehler vor erfolgreicher Anmeldung könnte ein eigenes QA-Konto zurückbleiben; nur dieses konkrete Konto entfernen.

2. Öffentlicher Stop/Start und idle Hardkill sind bestanden. Für künftige Prüfungen müssen nach Stop eigene API-/Modell-/Funnel-Prozesse weg sein. Kein globales `tailscale funnel reset/down`, keine fremden Prozesse stoppen. Tailscale-Dienst darf weiterlaufen.
3. Abschließende Prüfung mit eigener Python-Umgebung und portablem Node:

```powershell
.\.venv\Scripts\python.exe scripts\verify.py
```

Alternativ `check.bat`. Die automatischen Tests starten keine echten Modelle. OpenAPI nach API-Änderungen exportieren: `PYTHONPATH=backend`, `python -m chatabae.openapi`; dann `npm run generate:api` mit Node24. GitHub Actions prüft Schema-Drift ebenfalls.

4. Quellen-/Secret-Audit, Commit/Push, Actions **Verify**/**Publish website** und HTTP-Prüfung von Base-Path/API-Origin sind bestanden. Bei neuen Änderungen passende Prüfungen erneut ausführen. Produktionsartefakt weiterhin ausschließlich `frontend/dist`; private Konfiguration und Geheimnisse niemals veröffentlichen. `scripts/check_deployment.py` prüft den veröffentlichten Build lesend.
5. `docs/validation.md` und diese Übergabe auf den dann tatsächlichen Stand aktualisieren. Website-Link, Launcher und offene manuelle Abnahme knapp mitteilen.

## Noch offene externe/manuelle Grenzen

- Funnel-Berechtigung in Tailscale auf das Betreiberkonto bzw. dedizierten Knoten beschränken; Geräteschlüsselablauf für den Backend-Knoten abschalten. Diese Einstellungen wurden mangels authentifiziertem Zugriff auf die Webverwaltung nicht als umgesetzt bestätigt. Setup-/Betriebsdokumentation enthält die Schritte. Keine pauschale Tailnet-Policy überschreiben.
- Smartphone über Mobilfunk, echte gesperrte Drittanbieter-Cookies, visuelle 360-px-Abnahme, Fenster-X, Windows-Neustart und gemischter Langzeit-/Funnel-Durchsatztest fehlen noch als tatsächliche Gesamt-Abnahme. Idle Supervisor-Hardkill ist bestanden; die vollständige Matrix unter laufender gemischter Generierung bleibt gesondert offen.
- Die automatische Browserprüfung von localhost wurde durch eine Browser-Sicherheitsprüfung mit der Begründung eines unzulässigen URL-Protokolls abgelehnt. **Nicht mit einem anderen Browser, rohem CDP, nativer Automation oder indirektem Zugriff dieselbe Prüfung umgehen.** HTTP-/JSDOM-/Vertragstests sind zulässige eigenständige Prüfungen. Der Benutzer kann die Oberfläche selbst ansehen.
- Öffentliche Qwen-Bilder sind seit 13.10.2026 auf ausdrückliche Betreiberentscheidung freigegeben (Lizenzrisiko beim Betreiber). Die Bildmoderation nicht abschwächen; ihre Kalibrierung an schwierigen Beispielen steht noch aus. Pro Konto gilt weiterhin ein Bild je 5 Minuten und drei pro Tag.

## Wichtige Dateien

`README.md`, `docs/operations.md`, `docs/models.md`, `docs/model-manifest.md`, `docs/validation.md`, `docs/acceptance.md`, `THIRD_PARTY_NOTICES.md`; Launcher in `launcher/`; API und Jobs in `backend/chatabae/`; Oberfläche in `frontend/src/`; explizite Hardwaretests in `scripts/` und `scripts/models/`.

`setup.bat`, `start.bat`, `online.bat`, `offline.bat`, `admin.bat`, `backup.bat`, `check.bat` sind vorhanden. Normale Starts installieren oder downloaden nichts. Für weitere GPU-Tests erst den Supervisor stoppen, damit sich Modellprozesse nicht gegenseitig Speicher nehmen.
