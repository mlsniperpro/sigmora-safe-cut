# PRE-A $150 ledger (mirror of docs/API-NOTES.md §9.2; check with the awk line below)

| line | usd |
|---|---|
| probes (WP0) | 6.00 |
| build WP1 8 + WP4 6 + WP5 6 | 20.00 |
| WP2 cap (plan 8 x 3 x 0.59 = 14.16) | 15.00 |
| WP7 cap (plan 3 x 1.12 + 5 = 8.36) | 12.00 |
| test line 12 x 1.12 x 3 + 12 x 0.08 x 3 | 43.20 |
| recording code (PR #2) | 12.00 |
| pilots cap (PR #2) | 20.00 |
| public 6 days x 3 | 18.00 |
| healthz Oct 29 - Nov 4 budget line, rate-bounded (plan 7 x 288 x 0.000206 = 0.41) | 0.80 |

Check: `awk -F'|' '/^\| / && $3 ~ /[0-9]/{s+=$3} END{printf "TOTAL %.2f headroom %.2f\n", s, 150-s}' .agent/win/SAFECUT-PRE-A/calc/ledger.md`
