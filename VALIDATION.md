# Validation evidence

Development evidence; this is not a release acceptance report yet.

## 2026-11-10

- 59 automated tests pass (`python -m unittest discover -s tests`).
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
- Native Qt Quick UI verification passed with Tidal and Breeze at 200% scale:
  Enter, Shift+Enter, Esc, retained drafts, all settings categories and account form.
- Temporary KWin script/service test passed through KGlobalAccel: focus, hide,
  previous-window restoration, current-desktop preservation and centered geometry
  (304,34,832,592 on a 1440x900 logical screen with a 30px panel).
  Warm show was 25.63ms in this run; full installed acceptance will repeat it.
- Hotspot timer tested natively; exact 96px region and multiple output coordinates
  tested with the actual script under QJSEngine. Physical pointer activation still
  needs final installation verification.

The standalone popup uses PlasmaCore.Dialog with a utility-window role. This keeps
the native Plasma background/blur/slide behavior while allowing KWin to position
and focus it independently of a panel containment. The AppletPopup role ignored
absolute positioning in the native standalone test. The optional panel widget
will use Plasma's own containment popup.

Device/administrative adapters, optional widget, isolated browser,
installation/migration and Tidal capture/restore acceptance remain outstanding.
