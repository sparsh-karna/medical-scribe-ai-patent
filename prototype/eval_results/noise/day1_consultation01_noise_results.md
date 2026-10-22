# Noise stress test: day1_consultation01 (faster-whisper base.en, rule-based extractor)

| Condition | WER | Mean word prob (correct / wrong) | AUROC | Facts | Verified | Needs review | Rejected | Mean fact acoustic |
|---|---|---|---|---|---|---|---|---|
| clean | 16.2 % | 0.8822 / 0.6067 | 0.812 | 13 | 12 | 1 | 0 | 0.903 |
| snr20 | 27.9 % | 0.8489 / 0.5689 | 0.7999 | 11 | 8 | 3 | 0 | 0.809 |
| snr10 | 40.6 % | 0.783 / 0.4974 | 0.7846 | 9 | 5 | 3 | 1 | 0.727 |
| snr5 | 58.0 % | 0.7592 / 0.4903 | 0.7673 | 8 | 4 | 3 | 1 | 0.779 |
| snr0 | 70.6 % | 0.6967 / 0.4816 | 0.7191 | 5 | 2 | 3 | 0 | 0.702 |