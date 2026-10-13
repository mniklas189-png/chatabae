# Chatabae

Öffentliche Character-AI-Website mit einem ausschließlich lokal rechnenden Windows-Backend. GitHub Pages liefert die Oberfläche; Tailscale Funnel veröffentlicht die API nur, solange `online.bat` läuft.

## Einmal einrichten

Voraussetzungen: Windows 11, Python 3.12, NVIDIA-Treiber für die RTX 4070, persönliches Tailscale-Konto und das vorhandene `LocalImageAI`-Projekt neben diesem Ordner.

1. `setup.bat --models --voices --tailscale` starten. Das installiert Projektabhängigkeiten, eine eigene portable Node-24-Version und geprüft heruntergeladene Modellartefakte. Windows kann für Tailscale eine Administratorbestätigung verlangen.
2. In Tailscale anmelden. MagicDNS, HTTPS und Funnel einmal freischalten. Den Gerätenamen danach beibehalten. Geräteschlüsselablauf für den eigenen Backend-Knoten in der Tailscale-Verwaltung deaktivieren, wenn regelmäßige erneute Anmeldung vermieden werden soll.
3. `setup.bat --configure-only --api-url https://<gerät>.<tailnet>.ts.net` speichert die tatsächliche API-Adresse. Niemals eine dauerhafte `funnel --bg`-Freigabe anlegen.
4. Im GitHub-Repository die öffentliche Actions-Variable `VITE_API_BASE_URL` auf dieselbe Adresse setzen und **Publish website** einmal ausführen. Diese Konfiguration ist nur einmal nötig.

Bei vollständig eingerichteten Modellen: `start.bat` für lokale Entwicklung, `online.bat` für öffentlichen Betrieb und `offline.bat` zum Stoppen. Die Anwendung installiert beim normalen Start nichts und lädt keine Modelle aus dem Internet nach.

Die Website: [mniklas189-png.github.io/chatabae](https://mniklas189-png.github.io/chatabae/).

## Was gespeichert wird

Konten, Chats, Charaktere, Erinnerungen und Medien bleiben auf dem PC. `config/local.json` ist eine ignorierte lokale Installationsmarkierung und verweist auf den tatsächlichen privaten AppData-Ordner. So verwenden Start per Doppelklick und Start aus einer paketierten Entwicklungsumgebung dieselben Daten. Auch Geheimnisse, Logs, Laufzeitmodelle und Backups bleiben außerhalb des Repositorys.

Die öffentliche Bibliothek enthält nur freigegebene Profil-Snapshots. Private Anweisungen, Unterhaltungen und Stimmreferenzen gehören nicht dazu. Browser speichern keine privaten Chats dauerhaft; offline sind die Oberfläche und mitgelieferte Beispiele verfügbar. Der Betreiber des PCs hat technisch Zugriff auf die dort gespeicherten Daten.

## Modelle und Lizenzen

- Qwen3.5-9B Q4_K_M mit gepinntem llama.cpp-CUDA-Server für Chat und lokale Moderation.
- Vorhandene Qwen-Image-2.1-Dateien und ComfyUI werden wiederverwendet; Originalprojekt und Originalausgaben werden nicht verändert.
- Kokoro auf CPU für Englisch, Piper auf CPU für Deutsch, XTTS v2 für hochwertige Stimmen.
- Öffentliche Qwen-Image-Jobs sind standardmäßig serverseitig gesperrt. Nur tatsächliche lokale Evaluation ist vorgesehen, bis die öffentliche Nutzung dokumentiert erlaubt ist. `public_image_allowed` verlangt zusätzlich `public_image_license_evidence` in der privaten Konfiguration.
- XTTS v2 ist nur für die vereinbarte nichtkommerzielle Nutzung vorgesehen; seine Lizenz liegt neben den explizit heruntergeladenen Gewichten.

Downloadrevisionen, Dateigrößen und SHA-256-Prüfsummen stehen in `scripts/models/manage.py` und `scripts/bootstrap_runtime.py`. Bildergewichte werden nicht dupliziert. Anfängliche Quoten und die GPU-Warteschlange sind konfigurierbar; konkrete Besucherzahlen werden erst nach Messungen angegeben.

## Entwickeln und prüfen

```powershell
.\check.bat
```

Diese Prüfung verwendet die eigene Python-Umgebung und die portable Node-24-Version, unabhängig vom global installierten Node. Echte Inferenztests sind separat und ausdrücklich aufzurufen; `scripts/check_local.py` prüft einen vollständigen API-Ablauf mit einem anschließend gelöschten Testkonto. `scripts/load_scheduler.py --execute` misst den echten Chat-Scheduler mit 2, 5, 10 und 20 isolierten Testkonten. Während solcher GPU-Prüfungen muss Chatabae gestoppt sein, außer wenn der jeweilige Test ausdrücklich seine laufende lokale API prüft.

Details zur Einrichtung, zu Sicherheitsgrenzen, Backups, Wiederherstellung und Leistungsabnahme stehen unter `docs/`. GitHub Actions prüft Backend auf Windows/Linux und baut die statische Oberfläche. Nur `frontend/dist` wird veröffentlicht.
