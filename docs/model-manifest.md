# Modellmanifest

Stand: 13. Oktober 2026. Dieses Manifest beschreibt die ausgewählten lokalen Dateien und Herkunftsnachweise. `scripts/models/manage.py` enthält die Download-URLs, Bytegrößen und vollständigen SHA-256-Werte für ausdrücklich installierte Assets. Das Setup aktualisiert Modelle nicht automatisch. Eine vorhandene Datei wird wiederverwendet, bevor ein Download erwogen wird.

| Funktion | Modell / Laufzeit | Fixierte Herkunft | Lizenznachweis |
| --- | --- | --- | --- |
| Chat | Qwen3.5-9B, `Qwen3.5-9B-Q4_K_M.gguf` | [Unsloth GGUF, Revision `3885219b6810b007914f3a7950a8d1b469d598a5`](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/tree/3885219b6810b007914f3a7950a8d1b469d598a5) | GGUF-Karte nennt Apache-2.0 und verweist auf [Qwen3.5-9B LICENSE](https://huggingface.co/Qwen/Qwen3.5-9B/blob/main/LICENSE), Copyright 2026 Alibaba Cloud. |
| Bildprüfung | `mmproj-F16.gguf` für dasselbe Chatmodell | Dieselbe GGUF-Revision; CPU-Ausführung | Derselbe Modell-Lizenznachweis. |
| Chatserver | llama.cpp Windows CUDA 12.4 | [Release `b11429`](https://github.com/ggml-org/llama.cpp/releases/tag/b11429), beide Archive im Downloadmanifest | [MIT](https://github.com/ggml-org/llama.cpp/blob/b11429/LICENSE), Copyright 2023–2026 The ggml authors. CUDA-DLLs haben eigene [NVIDIA-Bedingungen](https://docs.nvidia.com/cuda/archive/12.4.1/eula/index.html). |
| Englische Sprache | Kokoro-82M v1.0, `kokoro-v1_0.pth`, Konfiguration und Stimmen | [Revision `f3ff3571791e39611d31c381e3a41a3af07b4987`](https://huggingface.co/hexgrad/Kokoro-82M/tree/f3ff3571791e39611d31c381e3a41a3af07b4987); installierter Snapshot wird bevorzugt | [Modellkarte: Apache-2.0 für Gewichte](https://huggingface.co/hexgrad/Kokoro-82M/blob/f3ff3571791e39611d31c381e3a41a3af07b4987/README.md). |
| Deutsche männliche Stimme | Piper `de_DE-thorsten-medium.onnx` und `.onnx.json` | Vorhandene lokale Installation; ONNX-Hash stimmt mit [Piper-Voices Revision `c10ece1aade47bb51c153c893d14e5bf8e5b7117`](https://huggingface.co/rhasspy/piper-voices/tree/c10ece1aade47bb51c153c893d14e5bf8e5b7117/de/de_DE/thorsten/medium) überein | [Thorsten-Modellkarte](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/de/de_DE/thorsten/medium/MODEL_CARD): Datensatz CC0, Fine-Tuning von Lessac medium; siehe Hinweise unten. |
| Deutsche weibliche Stimme | Piper `de_DE-kerstin-low.onnx` und `.onnx.json` | Dieselbe fixierte Piper-Voices-Revision; Download samt Modellkarte SHA-geprüft | [Kerstin-Modellkarte](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/de/de_DE/kerstin/low/MODEL_CARD): Datensatz CC0, Fine-Tuning von Ryan low; siehe Hinweise unten. |
| Optionale hochwertige Sprache | XTTS-v2, `model.pth`, `config.json`, `vocab.json`, `speakers_xtts.pth` | [Revision `6c2b0d75eae4b7047358e3b6bd9325f857d43f77`](https://huggingface.co/coqui/XTTS-v2/tree/6c2b0d75eae4b7047358e3b6bd9325f857d43f77) | [Coqui Public Model License 1.0.0](https://huggingface.co/coqui/XTTS-v2/blob/6c2b0d75eae4b7047358e3b6bd9325f857d43f77/LICENSE.txt); umfasst Modell und Ausgaben, nur nichtkommerzielle Nutzung. |

## Piper: Stimme, Trainingsdaten und ausführbares Programm

Die übergeordnete Piper-Voices-Repository-Metadaten nennen MIT. Der [Piper README](https://github.com/rhasspy/piper/blob/2023.11.14-2/README.md) verlangt ausdrücklich die Beachtung der einzelnen Modellkarten. Deshalb wird das Repository-Label hier nicht als pauschale Lizenzfreigabe aller Stimmen oder Trainingsbestandteile behandelt.

Thorsten Müller veröffentlicht seine [Thorsten-Voice-Datensätze unter CC0](https://github.com/thorstenMueller/Thorsten-Voice). Die Piper-Karte dokumentiert jedoch Fine-Tuning von [Lessac medium](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/en/en_US/lessac/medium/MODEL_CARD), dessen Karte auf die [Lessac/Blizzard-Datensatzlizenz](https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html) verweist. Diese Lizenz gewährt in §3.2 ausschließlich Forschungsnutzung ihrer definierten Materialien. §1.1 definiert darunter Aufnahmen, Texte, Prompts, Notizen und Labels; fertige neuronale Modellgewichte werden nicht ausdrücklich genannt. Damit ist eine eingeschränkte Datensatzherkunft belegt, aber nicht automatisch die Anwendung jeder Klausel auf das finale Thorsten-ONNX. Eine uneingeschränkte kommerzielle Freigabe des gesamten Trainingswegs wird hier ebenfalls nicht behauptet.

Der [Kerstin-Datensatz](https://github.com/rhasspy/dataset-voice-kerstin) ist CC0. Die [Ryan-low-Modellkarte](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/en/en_US/ryan/low/MODEL_CARD) nennt für den zugrundeliegenden Datensatz CC BY-NC-SA 4.0. Diese Herkunft wird zusätzlich zur Kerstin-Karte genannt; eine CC0-Angabe zu einem Fine-Tuning-Datensatz beseitigt nicht belegbar sämtliche Bedingungen vorheriger Bestandteile. Vor kommerzieller Nutzung oder Weiterverteilung der Stimme ist diese Lizenzkette zu klären. Für den unbezahlten Hobbybetrieb bleibt die Herkunft hier ausdrücklich dokumentiert.

Optional vorhandenes `en_US-danny-low` wird nur erkannt, wenn die lokale Datei existiert. Seine [Karte](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/en/en_US/danny/low/MODEL_CARD) verweist auf Mimic3, mit Ryan-low-Vortraining. Die dortige [CMU-Arctic-Lizenz](https://github.com/MycroftAI/mimic3-voices/blob/master/voices/en_US/cmu-arctic_low/LICENSE) erlaubt Nutzung und Veränderung, verlangt aber den Erhalt von Copyright-/Autorenhinweisen und die Kennzeichnung von Änderungen. Danny wird vom Setup nicht neu heruntergeladen; die standardmäßigen englischen Stimmen sind Kokoro.

Das vorhandene native `piper.exe` hat SHA-256 `96f3da3811151580073e40bb4dd20eb0fb8115f5f5f76e2fb54282b3edfa5c1f`. Die Datei besitzt keine eingebettete Produkt-/Versionsangabe; ihr genauer Build wurde nicht unabhängig einer Release-Datei zugeordnet. Der historische [Piper-Quellcode 2023.11.14-2](https://github.com/rhasspy/piper/blob/2023.11.14-2/LICENSE.md) ist MIT. Das ist getrennt von einem neueren Piper-Projekt oder dessen Lizenz zu betrachten. Das bereits vorhandene Paket enthält außerdem eSpeak NG; dessen [GPL-3.0-Lizenz](https://github.com/espeak-ng/espeak-ng/blob/master/COPYING) ist bei einer Weiterverteilung separat zu beachten. Chatabae verwendet die vorhandene Installation und verteilt sie nicht im Quellrepository.

Verifizierter Thorsten-ONNX-Hash: `7e64762d8e5118bb578f2eea6207e1a35a8e0c30595010b666f983fc87bb7819`. Lokaler Konfigurationshash: `974adee790533adb273a1ac88f49027d2a1b8f0f2cf4905954a4791e79264e85`.

## Vorhandene Qwen-Bildkomponenten

Die bestehende LocalImageAI-Installation wird unverändert gelesen. ComfyUI ist der vorhandene Commit `b0f4b7b294ce482a2e071d9d762c133d38c7aa07` (0.37.0), mit eigener Prozessinstanz und eigenen Chatabae-Verzeichnissen.

| Vorhandene Datei | Größe in Bytes | Veröffentlichter SHA-256 im Comfy-Org-Repository |
| --- | ---: | --- |
| `diffusion_models/qwen_image_2.1_int8_convrot.safetensors` | 7.256.783.064 | `cb74113cb03faecd79611b01fd7fd642f0aa60d6f0b95086abee214d75eaa57d` |
| `text_encoders/qwen3vl_8b_int8_convrot.safetensors` | 9.350.798.360 | `8bfd0f6e12abf2d2d697ecc888e5e90b0d6741d6708f05799f53afa560452e8f` |
| `vae/qwen_image_2.1_vae_bf16.safetensors` | 675.509.688 | `bb21f7473051e1ac368515dd3f2e15cd44d7a11748ee8823e1ddca3e4876b7c9` |

Quelle: [Comfy-Org/Qwen-Image-2.1, Revision `df94239739eef7205973a145ffa6f441f7b64e84`](https://huggingface.co/Comfy-Org/Qwen-Image-2.1/tree/df94239739eef7205973a145ffa6f441f7b64e84). Die lokal vorhandenen Namen und Größen stimmen überein. Die obigen Bildmodell-Hashes sind veröffentlichte Sollwerte, keine in dieser Prüfung berechneten lokalen Hashes; ein historischer Downloadbeleg für diese vorhandenen Dateien liegt nicht vor.

Die Repaketierungs-Karte verweist auf die [Qwen Research License](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE). Es wurde kein gesonderter Lizenztext gefunden, der den tatsächlich vorhandenen ConvRot-Encoder oder VAE unabhängig von diesem Paket freigibt. Die Lizenz eines anders verpackten Qwen3-VL-Modells belegt diese Ausnahme nicht.

Die Bildfunktion bleibt im öffentlichen Modus gesperrt. Die Lizenz definiert die zulässige nichtkommerzielle Nutzung als Forschung/Evaluation (§1(i), §2(a)); kommerzielle Nutzung benötigt eine gesonderte Lizenz (§2(b)). §9(a) behandelt Nutzung außerhalb der ausdrücklichen Erlaubnis ebenfalls separat. Ein kostenloser öffentlicher Unterhaltungsdienst lässt sich daraus nicht pauschal als erlaubte Evaluation ableiten. Eine dokumentierte Genehmigung oder eindeutig passende Alternative ist Voraussetzung einer späteren öffentlichen Freigabe. Es wurde kein anderes vollständig vorhandenes, eindeutig passendes Bildmodell gefunden.

## Reproduzierbarkeit der Sprachumgebungen

Die CPU-Umgebungen sind getrennt: Kokoro 0.9.4 / Misaki 0.9.4 / Torch und Torchaudio 2.8.0+cpu; XTTS verwendet `coqui-tts` 0.27.5 mit denselben CPU-Torch-Versionen. Die vollständigen Pins einschließlich Offline-spaCy-Modell stehen in `scripts/models/requirements-kokoro.txt` und `requirements-xtts.txt`. Die [MPL-2.0-Lizenz des Coqui-Programmcodes](https://github.com/idiap/coqui-ai-TTS/blob/v0.27.5/LICENSE.txt) ersetzt nicht die CPML der XTTS-Gewichte.
