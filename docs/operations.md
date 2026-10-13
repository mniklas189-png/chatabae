# Betrieb und Wiederherstellung

## Start und Stop

Die Batchdateien verwenden einen gemeinsamen Supervisor. Eine Mutex verhindert Doppelstart. Die API bindet auf 127.0.0.1:7810, die lokale Verwaltung auf 7811; Modelle und Entwicklungsfrontend bleiben auf Loopback. Portkonflikte führen zum Abbruch statt zu stillen Portwechseln.

`online.bat` prüft Tailscale-Anmeldung, konfigurierte öffentliche Adresse, vorhandene Serve/Funnel-Routen, GPU, Daten und Backend-Readiness. Anschließend startet es einen **Foreground** Funnel ohne `--bg` und prüft den öffentlichen Status mit der aktuellen Instanz-ID. Bestehende Freigaben werden nicht überschrieben.

`offline.bat` sendet einen authentifizierten lokalen Stop-Aufruf. Ctrl+C beendet die Anwendung ebenfalls. Ein Windows Job Object besitzt alle gestarteten Kinder einschließlich Modellprozessen, Frontend und Funnel-CLI; ein abruptes Supervisor-Ende beendet diesen Prozessbaum. Der installierte Tailscale-Dienst wird nicht gestoppt. Ein Fenster-Schließen beendet Kinder sofort, statt einen langen Drain zu versuchen. Unterbrochene Jobs werden beim nächsten Start erkannt.

Anwendung niemals über eine separat angelegte persistente Funnel-Route veröffentlichen: Diese könnte nach dem Ende der Foreground-Sitzung wieder sichtbar werden. `tailscale funnel reset` wird deshalb nicht automatisch verwendet.

## Einmalige Tailscale-Freigabe

Die Installation allein aktiviert Funnel noch nicht. Wenn die CLI „Funnel is not enabled“ meldet, den von ihr ausgegebenen Link im angemeldeten Betreiberkonto öffnen und die Freigabe abschließen. MagicDNS und HTTPS müssen ebenfalls aktiv sein. Die Anwendung setzt erst nach einem erfolgreichen öffentlichen Healthcheck den Status „Online“. [Offizielle Einrichtung](https://tailscale.com/docs/features/tailscale-funnel).

In der Tailscale-Verwaltung die Funnel-Node-Attribute auf das eigene Betreiberkonto begrenzen. Im vorhandenen `nodeAttrs`-Eintrag mit `attr: ["funnel"]` den pauschalen Zielwert `autogroup:member` durch die eigene Tailscale-Konto-ID ersetzen; andere vorhandene Richtlinien erhalten. Alternativ einen ausschließlich diesem Backend zugewiesenen Tag verwenden. Dadurch erhalten später hinzugefügte Mitglieder nicht automatisch dieselbe Veröffentlichungsberechtigung. [Node-Attribute](https://tailscale.com/docs/reference/syntax/policy-file).

Für den dedizierten Backend-PC unter **Machines → Gerät → Disable key expiry** den Geräteschlüsselablauf deaktivieren, wenn unbeaufsichtigte Starts dauerhaft ohne erneute Anmeldung funktionieren sollen. Diese kontogebundenen Einstellungen werden nicht ohne Zugriff auf die Tailscale-Verwaltung vorgenommen. Den Windows-Autostart von Tailscale kann man beibehalten; Chatabae selbst wird dadurch nicht öffentlich gestartet.

## Anmeldung

Passwörter werden ausschließlich auf der Backend-Origin eingegeben. PKCE und ein einmaliger, 60 Sekunden gültiger Code führen zurück zur statischen Oberfläche. Access-Tokens bleiben im Browser-Arbeitsspeicher. Bei gesperrten partitionierten Cookies erfolgt eine kurze erneute Navigation zum Backend; bei bestehender First-Party-Sitzung ist keine neue Passworteingabe nötig. Wiederherstellungscodes bei der Registrierung sicher aufbewahren.

## Backups

Vor Migrationen und täglich während des Betriebs wird ein konsistentes SQLite-Backup erstellt. Aufbewahrung: sieben tägliche und vier wöchentliche Sicherungen. Medien werden über ein Manifest zugeordnet. Nur gemeinsam gesicherte Datenbank und Medien wiederherstellen.

Vor Wiederherstellung `offline.bat` ausführen. Den aktuellen Datenordner separat sichern. Das ausgewählte Backup in einen neuen Datenordner wiederherstellen, den lokalen Konfigurationspfad darauf einstellen und zunächst lokal testen. Ein Backup im selben Laufwerk schützt nicht vor Laufwerksausfall; eine zusätzliche private Sicherung auf einem anderen Datenträger ist sinnvoll.

`backup.bat` verwendet denselben privaten Datenordner wie die Startdateien. Beispiel in einer PowerShell im Projektordner:

```powershell
.\backup.bat create
.\backup.bat verify "C:\Pfad\zum\daily-Backup"
.\offline.bat
.\backup.bat restore "C:\Pfad\zum\daily-Backup" --data-dir "C:\Pfad\zur\Wiederherstellung"
```

Die Wiederherstellung prüft alle Prüfsummen und die Medienzuordnung. Bestehende Daten werden unter einem datierten Namen aufbewahrt. Sitzungen werden widerrufen und unterbrochene Aufträge beendet. Ein laufendes Backend im Zielordner verhindert die Wiederherstellung. Für einen neuen Zielordner die private Konfiguration übernehmen und anschließend `setup.bat --configure-only --data-dir "C:\Pfad\zur\Wiederherstellung"` ausführen.

## Diagnose

Logs stehen im privaten Datenordner unter `logs/`. Sie enthalten Betriebszustände; private Prompts und Sitzungstoken sollen nicht geloggt werden. Die Terminalanzeige und lokale Verwaltung zeigen Job-/Modellzustände. Ein 429 bedeutet eine erreichte konfigurierte Grenze; ein 503 eine derzeit nicht verfügbare Funktion. Ein gestörter Bildprovider darf vorhandene Gespräche nicht unlesbar machen.

Tailscale Funnel ist Beta und besitzt nicht konfigurierbare Bandbreitengrenzen. Es wird keine unbegrenzte Bandbreite oder garantierte Verfügbarkeit versprochen. Namen von Gerät und Tailnet nach Einrichtung nicht verändern, sonst muss die API-Konfiguration einmal aktualisiert werden.
