# Hinweise auf Drittanbieter

Die lokalen Modelle und Laufzeiten bleiben eigenständige Bestandteile mit eigenen Lizenzen. Diese Übersicht ersetzt die Originaltexte nicht. Fixierte Revisionen, Dateihashes und ungeklärte Herkunftsgrenzen stehen im [Modellmanifest](docs/model-manifest.md).

| Bestandteil | Urheber / Projekt | Original-Lizenz oder Modellkarte |
| --- | --- | --- |
| Qwen3.5-9B und zugehöriger Vision-Projektor (Moderation) | Alibaba Cloud / Qwen; GGUF-Bereitstellung Unsloth | [Apache-2.0](https://huggingface.co/Qwen/Qwen3.5-9B/blob/main/LICENSE); Copyright 2026 Alibaba Cloud. |
| Huihui-Qwen3.5-9B-abliterated und Vision-Projektor (Chat) | huihui-ai auf Basis von Alibaba Cloud / Qwen; GGUF-Bereitstellung mradermacher | [Apache-2.0](https://huggingface.co/huihui-ai/Huihui-Qwen3.5-9B-abliterated); Copyright 2026 Alibaba Cloud. |
| llama.cpp b11429 | The ggml authors | [MIT](https://github.com/ggml-org/llama.cpp/blob/b11429/LICENSE); Copyright 2023–2026. |
| CUDA-12.4-Laufzeitbibliotheken | NVIDIA | [CUDA Toolkit EULA](https://docs.nvidia.com/cuda/archive/12.4.1/eula/index.html); Weiterverteilung nur im Rahmen der jeweiligen Redistributable-Bedingungen. |
| Kokoro-82M v1.0 und Stimmen | hexgrad / Kokoro contributors | [Apache-2.0-Modellkarte](https://huggingface.co/hexgrad/Kokoro-82M/blob/f3ff3571791e39611d31c381e3a41a3af07b4987/README.md). |
| Vorhandene Piper-Laufzeit | Michael Hansen / rhasspy; genauer lokaler Build nicht zugeordnet | [Historischer MIT-Lizenztext](https://github.com/rhasspy/piper/blob/2023.11.14-2/LICENSE.md); Copyright 2022 Michael Hansen. |
| Thorsten-Stimme / Sprachdaten | Thorsten Müller, Piper contributors; Lessac-Vortraining | [Thorsten CC0-Datensatz und Modellkarte](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/de/de_DE/thorsten/medium/MODEL_CARD), [Lessac-Karte](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/en/en_US/lessac/medium/MODEL_CARD). |
| Kerstin-Stimme / Sprachdaten | Kerstin, rhasspy / Piper contributors; Ryan-Vortraining | [Kerstin CC0-Datensatz und Modellkarte](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/de/de_DE/kerstin/low/MODEL_CARD), [Ryan-Datensatz CC BY-NC-SA 4.0](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/en/en_US/ryan/low/MODEL_CARD). |
| Optional erkannte Danny-Stimme | Piper / MycroftAI / Carnegie Mellon University; Ryan-Vortraining | [Danny-Karte](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/en/en_US/danny/low/MODEL_CARD), [CMU-Arctic-Bedingungen](https://github.com/MycroftAI/mimic3-voices/blob/master/voices/en_US/cmu-arctic_low/LICENSE), Copyright 2003 Carnegie Mellon University. |
| eSpeak NG im vorhandenen Piper-Paket | eSpeak NG contributors | [GPL-3.0](https://github.com/espeak-ng/espeak-ng/blob/master/COPYING). |
| XTTS-v2-Gewichte und generierte Audiodateien | Coqui | [Coqui Public Model License 1.0.0](https://huggingface.co/coqui/XTTS-v2/blob/6c2b0d75eae4b7047358e3b6bd9325f857d43f77/LICENSE.txt). |
| Coqui-TTS-Programmcode 0.27.5 | Coqui / Idiap / contributors | [MPL-2.0](https://github.com/idiap/coqui-ai-TTS/blob/v0.27.5/LICENSE.txt). |
| Qwen Image 2.1, vorhandenes Comfy-Org-Paket | Alibaba Cloud / Qwen / Comfy-Org | [Qwen Research License](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE); öffentliche Bildfunktion auf Betreiberentscheidung freigegeben, Lizenzrisiko beim Betreiber. |

Apache-/MIT-Lizenztexte, Copyrights und etwaige NOTICE-Dateien müssen bei einer Weiterverteilung entsprechend ihren Bedingungen erhalten bleiben. Diese Quellenliste allein ist kein vollständiges Lizenzpaket für die Weiterverteilung sämtlicher externer Binärdateien. Vorhandene LocalImageAI- und Piper-Installationen werden referenziert und nicht in diesem Quellrepository gebündelt.

XTTS-v2 ist optional und für den vereinbarten unbezahlten Hobbybetrieb vorgesehen. Die CPML erfasst ausdrücklich sowohl das Modell als auch dessen Ausgaben. Ihre Definition nichtkommerzieller Zwecke umfasst Hobbyprojekte, solange keine direkte oder indirekte Bezahlung aus Modell- oder Ausgabenutzung entsteht. Jeder Empfänger von Modellteilen oder erzeugten Ausgaben muss den Lizenztext oder seine URL erhalten. Daher ist bei XTTS-Audio die obige CPML-URL mitzuliefern; eine spätere Monetarisierung erfordert eine gesonderte Prüfung.

Die CC0-Angabe einzelner Piper-Datensätze ist getrennt von der Herkunft vortrainierter Gewichte zu lesen. Das Modellmanifest dokumentiert die Lessac-/Ryan-Linie; insbesondere wird Ryan nicht als uneingeschränkt kommerziell nutzbar ausgegeben. Für eine spätere Weiterverteilung oder kommerzielle Nutzung sind die offenen Lizenzketten vorher zu klären.
