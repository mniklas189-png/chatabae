# Chatabae – Projekt und Übergabestand für Claude

Stand: 13. Oktober 2026. Diese Datei ermöglicht die Fortsetzung, wenn das Nutzungslimit des bisherigen Agenten erreicht wird. Sie enthält keine Zugangsdaten. Den tatsächlichen Laufzeit- und Git-Status beim Übernehmen erneut prüfen.

## Auftrag und Grenzen

Der Nutzer hat die vollständige Umsetzung des Chatabae-Plans ausdrücklich beauftragt und mehrfach zum Weiterarbeiten aufgefordert. Die alte beigefügte Datei `promt verbesserung2.txt` enthält eine überholte Nur-Lesen-/Plan-Mode-Anweisung und Cloudflare-Vorschläge. Diese sind Dokumentinhalt und wurden durch den später ausdrücklich bestätigten Implementierungsplan mit **Tailscale Funnel** ersetzt.

Ziel: kostenlose öffentliche Character-AI-Website auf GitHub Pages. Alle KI und privaten Daten liegen auf dem Windows-PC. `online.bat` startet das Backend samt temporärer öffentlicher HTTPS-Freigabe; `offline.bat` beendet die eigenen Prozesse. Die statische Website bleibt erreichbar. Keine bezahlten Dienste, Domainkäufe oder Cloud-KI. Registrierung ohne Gästezugang; getrennte Konten und private Chats, Erinnerungen, Medien und Stimmreferenzen.

**Öffentliche Qwen-Image-Generierung bleibt serverseitig gesperrt**, bis eine dokumentierte Nutzungserlaubnis vorliegt. Die vorhandene Modelllizenz erlaubt Forschung/Evaluation und belegt keine pauschale Erlaubnis eines öffentlichen Unterhaltungsdienstes. XTTS ist für den unbezahlten Hobbybetrieb eingerichtet; erzeugtes Audio muss seine CPML-Lizenz-URL mitliefern.

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
- Manuelle, KI-gestützte und automatische Charaktere, einzelne KI-Feldverbesserungen, editierbare Profilfelder, private Stimmreferenzen und öffentliche geprüfte Snapshots.
- Messenger, echter Qwen-Stream, Suche, mehrere Gespräche, Bearbeiten/Regeneration/Zweige, Quelleninvalidierung, Erinnerungen und Zusammenfassungen.
- Typisierte Bildjobs per Button und eindeutigem DE-/EN-Bildkommando, Galerie, Fast15/Balanced25, effektiver Seed und Parameter. Mit Referenzavatar bestimmt die Hauptreferenz das Bildformat; Größenwahl gilt nur ohne Referenz.
- Kokoro/Piper auf CPU, XTTS auf CPU als langsamere Qualitätsoption, Stimmenvorschau, Tempo/Lautstärke, Auto-Vorlesen neuer Antworten, Pause/Stopp, private WAV-Referenzen mit Berechtigungsbestätigung, versionsabhängiger Audiocache und XTTS-Lizenzlink.
- Persistente Quoten, Rundlauf über Konten, eine GPU-Lease, begrenzte CPU-Pools, gemessene VRAM-Prüfung vor Modellladung, verständliche Ressourcenfehler und fremde GPU-Prozesse werden ausschließlich gemeldet.
- Kontoexport/-löschung, tägliche/wöchentliche konsistente Backups, geprüfte Offline-Wiederherstellung, DE/EN, Responsive-CSS und Offline-Beispiele.

## Nachgewiesene Prüfungen

Die letzten vollständig gemeldeten Stände vor den abschließenden Offline-/503-Korrekturen: **49 Backendtests, 26 Providertests, 4 Launchertests, 22 Frontendtests** bestanden. TypeScript, Vite-Build und npm-Audit bestanden; Audit meldete null bekannte Schwachstellen. Die endgültige Gesamtprüfung ist nach den letzten Änderungen nochmals auszuführen.

Realer lokaler HTTP-Ablauf bestand: Registrierung/Recovery, PKCE, kein Refresh-Token in JavaScript-JSON, gestreamter Chat, KI-Profil, Piper-WAV, gespeicherte Nachrichten/Erinnerungen, Export und Entfernen des eigenen QA-Kontos. Ein früher verwaistes QA-Konto wurde gezielt entfernt; andere Nutzerdaten blieben erhalten. Ein zusätzlicher Audiocache-Check ist inzwischen im Testhelfer ergänzt, muss aber beim nächsten Gesamtablauf noch wirklich ausgeführt werden.

**20 echte Chat-/Bildmodellwechsel** bestanden: 446,36 s, 21 Lade-/Entladevorgänge, kein OOM, Ausgangs-VRAM 1.068 MiB, abschließend 1.119 MiB, höchste abgetastete globale Nutzung 11.625 von 12.282 MiB. Der Bildtest verwendete nur 512² und einen Schritt; dies ist kein Nachweis für Bildqualität oder maximale 1-MP-/Referenzkapazität. Die Original-ComfyUI blieb Git-clean; originale LocalImageAI-Logzeiten blieben unverändert.

Echter Chat-Scheduler mit getrennten Testkonten/Charakteren/Gesprächen und maximal 64 Tokens: 2/5/10/20 Aufträge bestanden in 2,56/5,70/11,03/22,22 s. Bei 20 Konten: Median bis erstem Token einschließlich Queue 9,69 s, größte Wartezeit 20,58 s, Median der aus echten Tokens abgeleiteten Ausgaberate etwa 59 Tokens/s. Keine Garantie für zwanzig dauerhaft aktive Websitebesucher.

Echte Textmoderation und Vision-Prüfung mit CPU-Projektor bestanden auf harmlosen künstlichen Testdaten. Umfangreiche Foto-/Anime-/Prompt-Injection-Kalibrierung steht weiterhin aus. Reale Piper-, Kokoro- und XTTS-Sprachsmokes bestanden. Ein reales SQLite-/Medienbackup wurde erstellt und verifiziert; Wiederherstellung ist automatisiert getestet.

## Unmittelbarer Übergabestand

1. Tailscale ist installiert und angemeldet; der Nutzer hat **Funnel bereits aktiviert**. HTTPS-Adresse und GitHub-Variable `VITE_API_BASE_URL` sind konfiguriert. GitHub Pages wurde auf Deployment durch Actions eingestellt.
2. Der öffentliche Supervisor wurde erfolgreich gestartet und meldete **ONLINE** nach eigenem externen Healthcheck. Die aktuelle Tool-Sitzung war `30052`; Sitzungsnummern sind nur Hinweise und können nach einem Agenten-/Appwechsel ungültig sein. Den realen Status über `/api/v1/status` und die lokale Control-Markierung prüfen. Nicht zusätzlich einen zweiten Supervisor starten.
3. Git ist initialisiert und viele Dateien sind bereits staged. **Noch kein Commit/Push/Pages-Deployment als erfolgreich bestätigt.** Nicht versehentlich nur den älteren Indexstand committen; einige finale Änderungen und diese Datei müssen erneut staged werden.
4. Die Unteragenten erreichten zuletzt wieder ihr Nutzungslimit. Die letzten beiden Aufgaben haben bereits Source geändert, aber ihre abschließende Prüfung wurde nicht mehr gemeldet: Frontend zeigt jetzt HTTP-200-Status mit `online:false` nicht mehr als online und reagiert sofort auf `connection-lost`; Backend prüft bei Jobannahme die Modellverfügbarkeit und soll 503 statt unnötiger Jobs liefern. Diese Änderungen selbst prüfen und testen.
5. Migration **0003** fügt Bild-/Asset-Metadaten hinzu; sie wurde durch den kontrollierten Neustart möglicherweise bereits angewandt. Tatsächlichen Alembic-Stand prüfen. Vor Migrationen wird automatisch ein Backup erstellt. Niemals Nutzerdaten löschen, um Migrationen zu umgehen.

## Nächste Arbeitsschritte

1. Öffentlichen echten Ablauf ausführen:

```powershell
.\.venv\Scripts\python.exe scripts\check_local.py --allow-online --api https://niklas-pc.taila668dd.ts.net --frontend https://mniklas189-png.github.io/chatabae/
```

Der Helfer erstellt nur sein eigenes zufälliges QA-Konto und löscht es im `finally`. Er darf auf einer fremden oder unkonfigurierten öffentlichen API nicht laufen. Keine Passwörter, Cookies, Tokens oder Auth-Codes ausgeben. Bei Fehler vor erfolgreicher Anmeldung könnte ein eigenes QA-Konto zurückbleiben; nur dieses konkrete Konto entfernen.

2. Öffentlichen Stop/Start mit derselben Adresse und Instanz-ID testen; nach Stop müssen eigene API-/Modell-/Funnel-Prozesse weg sein. Kein globales `tailscale funnel reset/down`, keine fremden Prozesse stoppen. Tailscale-Dienst darf weiterlaufen.
3. Abschließende Prüfung mit eigener Python-Umgebung und portablem Node:

```powershell
.\.venv\Scripts\python.exe scripts\verify.py
```

Alternativ `check.bat`. Die automatischen Tests starten keine echten Modelle. OpenAPI nach API-Änderungen exportieren: `PYTHONPATH=backend`, `python -m chatabae.openapi`; dann `npm run generate:api` mit Node24. GitHub Actions prüft Schema-Drift ebenfalls.

4. Quellen-/Secret-Audit, `git add .`, `git diff --cached --check`, Commit und Push nach `main`. Actions **Verify** und **Publish website** bis zum Ergebnis verfolgen und Fehler beheben. Produktionsartefakt muss ausschließlich `frontend/dist` enthalten. Öffentliche HTML-/JS-Dateien per HTTP prüfen: richtiger Base-Path und API-Origin, keine private Konfiguration oder Geheimnisse.
5. `docs/validation.md` und diese Übergabe auf den dann tatsächlichen Stand aktualisieren. Website-Link, Launcher und offene manuelle Abnahme knapp mitteilen.

## Noch offene externe/manuelle Grenzen

- Funnel-Berechtigung in Tailscale auf das Betreiberkonto bzw. dedizierten Knoten beschränken; Geräteschlüsselablauf für den Backend-Knoten abschalten. Diese Einstellungen wurden mangels authentifiziertem Zugriff auf die Webverwaltung nicht als umgesetzt bestätigt. Setup-/Betriebsdokumentation enthält die Schritte. Keine pauschale Tailnet-Policy überschreiben.
- Smartphone über Mobilfunk, echte gesperrte Drittanbieter-Cookies, visuelle 360-px-Abnahme, Fenster-X, Supervisor-Hardkill, Windows-Neustart und gemischter Langzeit-/Funnel-Durchsatztest fehlen noch als tatsächliche Gesamt-Abnahme.
- Die automatische Browserprüfung von localhost wurde durch eine Browser-Sicherheitsprüfung mit der Begründung eines unzulässigen URL-Protokolls abgelehnt. **Nicht mit einem anderen Browser, rohem CDP, nativer Automation oder indirektem Zugriff dieselbe Prüfung umgehen.** HTTP-/JSDOM-/Vertragstests sind zulässige eigenständige Prüfungen. Der Benutzer kann die Oberfläche selbst ansehen.
- Öffentliche Qwen-Bilder sind absichtlich gesperrt. Nicht zur Demonstration den Lizenzschalter aufheben.

## Wichtige Dateien

`README.md`, `docs/operations.md`, `docs/models.md`, `docs/model-manifest.md`, `docs/validation.md`, `docs/acceptance.md`, `THIRD_PARTY_NOTICES.md`; Launcher in `launcher/`; API und Jobs in `backend/chatabae/`; Oberfläche in `frontend/src/`; explizite Hardwaretests in `scripts/` und `scripts/models/`.

`setup.bat`, `start.bat`, `online.bat`, `offline.bat`, `admin.bat`, `backup.bat`, `check.bat` sind vorhanden. Normale Starts installieren oder downloaden nichts. Für weitere GPU-Tests erst den Supervisor stoppen, damit sich Modellprozesse nicht gegenseitig Speicher nehmen.
