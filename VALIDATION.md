# Validation evidence

Development evidence; this is not a release acceptance report yet.

## 2026-11-10

- 77 automated tests pass (`python -m unittest discover -s tests`).
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
- Optional `.plasmoid` package built and installed into a disposable data directory;
  `plasmawindowed` loaded it without QML errors. Its actual QML D-Bus bridge passed
  snapshot, pushed updates, send, paginated history and missing-service checks.

The standalone popup uses PlasmaCore.Dialog with a utility-window role. This keeps
the native Plasma background/blur/slide behavior while allowing KWin to position
and focus it independently of a panel containment. The AppletPopup role ignored
absolute positioning in the native standalone test. The optional panel widget
will use Plasma's own containment popup.

- Real isolated browser checks pass: HTTPS through the proxy, page read/scroll,
  verified download delivery, blocked local/file/account URLs, no home/session-bus/
  key/direct-network access, visible-session retention and hidden-idle termination.
- Gateway tests reject private/mixed DNS responses and pin public numeric addresses.
- Native Wayland browser opens independently; its selected UI fonts are copied to
  an ephemeral profile instead of exposing the personal font/config tree.
- Approval tests cover refusal, one-use grants, changed plans, restart expiry and
  agent pause/resume. Package and CUPS tests use disposable service fixtures.
- Real PackageKit preview resolved a configured-repository package without installing
  it. Installing the required python-pycups dependency through the adapter then
  passed normal system authentication and exact installed-version verification.
- Real CUPS read found the existing printer and no queued jobs; no printer state
  was modified. No removable hardware was available, so USB changes use fixtures.
- Fixed kernel and USB-hardware commands execute inside Bubblewrap.

Installation/migration, broader hardware/window-control checks, browser interaction
fixtures and Tidal capture/restore acceptance remain outstanding.
