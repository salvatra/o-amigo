# Validation evidence

Development evidence; this is not a release acceptance report yet.

## 2026-11-10

- 52 automated tests pass (`python -m unittest discover -s tests`).
- Real Bubblewrap runs: qpdf page reordering/splitting/checking, Poppler text,
  ZIP round-trip, TAR/ZIP malicious-entry rejection, manual reading.
- HTTP fixtures: byte-fragmented Portuguese UTF-8, fragmented tool arguments,
  incomplete streams, cancellation, HTTP 401/402/404/429/503, citations and usage.
- Durable task tests: sequential tools, no duplicate mutations, restart uncertainty,
  continuation counters, search reservation, missing usage and paginated history.
- One real OpenRouter request: exact DeepSeek model, default price ceilings,
  Parallel Fast with `max_uses: 1`. Provider Wafer, one search, five citations,
  2.695 seconds, API-reported total cost USD 0.001301652.
  Credentials were retrieved in memory from Secret Service; no response or key
  was saved in this repository.
- Gitleaks scan of source tree passed before publication.

Native production UI, device/administrative adapters, isolated browser,
installation/migration and Tidal capture/restore acceptance remain outstanding.
