# Vocabulary biasing A/B (faster-whisper base.en)

| Consultation | Mode | WER | Subs | Del | Ins | Segments | Medical terms correct |
|---|---|---|---|---|---|---|---|
| day1_consultation01 | none | 16.2 % | 101 | 80 | 32 | 185 | 26 / 32 |
| day1_consultation01 | initial_prompt | 19.4 % | 111 | 112 | 33 | 178 | 26 / 32 |
| day1_consultation01 | hotwords | 27.9 % | 97 | 137 | 134 | 126 | 30 / 32 |

| Mode (pooled) | WER | Deletions | Medical terms correct |
|---|---|---|---|
| none | 16.1 % | 80 | 26 / 32 (81 %) |
| initial_prompt | 19.4 % | 112 | 26 / 32 (81 %) |
| hotwords | 27.9 % | 137 | 30 / 32 (94 %) |