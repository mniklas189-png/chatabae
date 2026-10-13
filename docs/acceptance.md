# Abnahme auf der Zielhardware

Automatische Tests verwenden ausdrücklich injizierte Testprovider. Ein bestandener Test ist keine Bestätigung einer realen GPU- oder Funnel-Messung.

## Lokale Integrationen

- Qwen: realer deutscher und englischer Chat, Textstream, begrenzter Kontext, Abbruch, Regeneration.
- Stimmen: männlich/weiblich in DE/EN, Kokoro/Piper CPU und XTTS, Pause/Stop, Cache.
- Bilder: tatsächliche private Evaluation mit stabiler Hauptreferenz, gespeicherter Seed, getrennte Input/Output-Verzeichnisse und unverändertes LocalImageAI.
- Wechsel: mindestens 20 wiederholte Chat/Bild/XTTS-Wechsel; VRAM nach Entladen messen, RAM darf nicht stetig steigen.

## Öffentlicher Betrieb

Mit einem Smartphone über Mobilfunk und ohne Tailscale-App prüfen: dieselbe HTTPS-Adresse nach Start/Stop/Start; Anmeldung; mindestens zweiminütiger Stream; Abbruch; private Datenzugriffe; Offline-Erkennung. Ctrl+C, Fenster-X, Supervisor-Hardkill, Modellabsturz und Windows-Neustart prüfen. Öffentliches Backend muss nach Stop innerhalb von zehn Sekunden unerreichbar sein und darf nach Reboot nicht automatisch wiederkehren.

## Last

Stufen mit 2, 5, 10 und 20 Konten, mehreren Tabs und gemischten Jobs ausführen. Warteschlange, Fairness, Quotenpersistenz, Zeit bis zum ersten Token, Tokens/s, TTS-Latenz, GPU/RAM-Spitzen und Funnel-Durchsatz erfassen. Tests bei Queueüberlauf, OOM, niedriger freier Disk und Tunnelverlust wiederholen. Eine Benutzerkapazität erst nach diesen Messungen nennen.

## Inhalte und Daten

Moderation mit DE/EN, harmloser Romantik, Foto/Anime, verschiedenen Hauttönen, zitierter problematischer Sprache und Prompt-Injection prüfen. Ausfall oder unklare Entscheidung muss Veröffentlichung zurückhalten. Meldebrigaden dürfen keine beliebigen globalen Löschungen auslösen. Fremde IDs, manipulierte Pfade, MIME-Spoofing, SVG, EXIF-GPS und Dekompressionsbomben testen. Datenbank und Medien gemeinsam aus Backup wiederherstellen.
