# Lokale Modelle

Chatabae verwendet eigene Modellprozesse und eigene Laufzeitverzeichnisse. Die vorhandene LocalImageAI-Installation und ihre Gewichte werden gelesen; ihre Konfiguration, Eingaben, Ausgaben und Datenbank werden nicht verändert. Modellgewichte werden nur durch den ausdrücklich gestarteten Setup-Schritt heruntergeladen.

## Chat und Moderation

Qwen3.5-9B Q4_K_M läuft über den lokalen llama.cpp-Server. Der Standardkontext beträgt 8.192 Tokens bei einem gleichzeitigen GPU-Auftrag. Vor der Anfrage zählt Chatabae den tatsächlichen Modellprompt mit `/apply-template` und `/tokenize`. Ausgabetokens und ein kleiner Rahmenpuffer bleiben frei. Ältere vollständige Gesprächsrunden werden bei Bedarf ausgelassen; Systemregeln und die neueste Nachricht werden erhalten. Wenn bereits Profil, Erinnerungen und neueste Nachricht zu groß sind, schlägt die Anfrage verständlich fehl.

Avatarprüfungen verwenden den lokalen Vision-Projektor auf der CPU. Für ein Bild werden bis zu 1.024 zusätzliche Tokens reserviert. Unsichere oder fehlgeschlagene Prüfungen halten eine Veröffentlichung zur manuellen Prüfung zurück.

## Bilder und Referenzporträts

Qwen Image 2.1 verwendet die vorhandenen INT8-Gewichte mit dynamischem GPU-/RAM-Offloading. Standardmäßig werden ein Bild, etwa ein Megapixel und bis zu drei Referenzen verwendet. Die eigene ComfyUI-Engine reserviert zusätzlich 0,8 GiB VRAM und deaktiviert gepinnten Speicher. Chat- und Bildmodelle belegen die GPU nacheinander.

Nach dem Beenden eigener GPU-Prozesse liest Chatabae die tatsächliche NVIDIA-Speicherbelegung. Vor dem nächsten Laden wartet es begrenzt auf ausreichend freien Speicher; fehlende Messwerte oder zu wenig freier Speicher halten den Auftrag mit einer verständlichen Fehlermeldung zurück. Der Chat-Ladebedarf berücksichtigt die GGUF-Größe, 512 MiB Arbeitsbudget und mindestens 1.536 MiB Reserve. Der Bildpfad fordert mindestens 8.192 MiB freien VRAM und verwendet Comfys dynamisches Offloading mit 0,8 GiB Reserve. Desktopbelegung und diese Reserve ergeben auf dem geprüften Rechner etwa 1,8 GiB. Das ist ein Lade-/Offloading-Budget, keine garantierte freie Speichermenge während jeder Modelloperation. Fremde GPU-Prozesse werden nur erfasst; Chatabae beendet sie nicht. Öffentliche Statusantworten enthalten lediglich deren Anzahl.

**Mit Referenzporträt bestimmt das erste Referenzbild das Seitenverhältnis und die Bildaufteilung.** Es wird auf etwa ein Megapixel skaliert. Die Breiten- und Höhenoptionen gelten bei diesem Referenz-/Editpfad nicht; sie gelten für Bilder ohne Referenz. Der vom Qwen-Encoder erzeugte Latent bleibt an die erste Referenz angepasst, damit die Bearbeitung nicht gegenüber dem Ausgangsbild verschoben wird. Identitätserhalt ist ein Modellziel und keine Garantie.

Die öffentliche Qwen-Bildfunktion bleibt ohne dokumentierte Nutzungserlaubnis gesperrt. Der vorhandene Adapter kann für private Evaluation verwendet werden. Kostenloser öffentlicher Betrieb ist nicht pauschal von der auf Forschung/Evaluation beschränkten Lizenz abgedeckt. [Qwen Research License](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE).

## Sprache

Kokoro verwendet einen persistenten eigenen CPU-Prozess mit Modell-, Sprach- und Stimmcache. Er wird beim Serverstart vorgewärmt. Englische weibliche und männliche Stimmen kommen aus lokalen Gewichten; deutsche Stimmen verwenden Piper. XTTS ist eine optionale CPU-Qualitätsstufe mit längerer Laufzeit und eigener Umgebung. Ein GPU-Modellwechsel beendet diese CPU-Sprachprozesse nicht. Abbruch beendet nur den betroffenen eigenen Sprachprozess; der nächste Auftrag kann ihn neu starten.

## Reproduzierbare Prüfung

`scripts/models/smoke.py` führt ausdrücklich ausgewählte echte Inferenzprüfungen aus. `scripts/models/benchmark.py --execute` prüft 20 tatsächliche Wechsel zwischen Chat und Bildmodell und schreibt einen privaten JSON-Bericht mit Laufzeiten und Speicherbeobachtungen. Vorher muss die GPU für diesen Test frei sein. Der Bildtest mit 512 × 512 Pixeln und einem Schritt prüft Modellladen, Inferenz und Freigabe; er bewertet weder Bildqualität noch die maximal mögliche Auflösung.

Am 13. Oktober 2026 bestanden alle 20 Wechsel auf einer RTX 4070 (12.282 MiB) in 446,36 Sekunden. Einschließlich Erstladen und Abschlussfreigabe gab es 21 Ladevorgänge und 21 Entladungen. Bildwechsel benötigten durchschnittlich 33,00 Sekunden, Chatwechsel 5,98 Sekunden. Die abgetastete globale VRAM-Spitze lag bei 11.625 MiB; vor erneutem Laden lag die Belegung zwischen 1.057 und 1.137 MiB. Start-/Endbelegung: 1.068/1.119 MiB. Der mindestens beobachtete freie Arbeitsspeicher lag bei 12.660 MiB. Es trat kein OOM auf und der Test erkannte keinen anhaltenden Speicheranstieg. Das ist keine Zusage für 1-Megapixel-Referenzbilder oder parallele fremde GPU-Anwendungen. Der private Bericht heißt `benchmarks/20261013T101454Z-a24862b4/gpu-switches.json` unter dem konfigurierten Datenverzeichnis.

Die Modellherkunft und Lizenzgrenzen sind im [Modellmanifest](model-manifest.md) und den [Drittanbieterhinweisen](../THIRD_PARTY_NOTICES.md) dokumentiert.
