# Validation evidence — 0.1.0

Acceptance performed on Arch Linux, Plasma/KWin 6.8.2, Qt 6.12 and Wayland,
2026-11-10. This separates real checks from service fixtures and hardware limits.

## Automated and isolated checks

- 85 tests pass: fragmented Portuguese UTF-8/SSE/tool arguments, incomplete streams,
  cancellation, HTTP 401/402/404/429/503, price caps, exact model and usage handling.
- Durable sequential tasks: restart uncertainty, no mutation replay, continuation
  counters, tool/search budgets, missing usage and paginated history.
- Policy: protected paths, escaping symlinks/hardlinks, special files, option and
  command injection, schema validation and absence of a model policy-edit tool.
- Recovery: atomic writes, timestamp restoration, changed-target conflicts,
  retention/quota, 64 MiB verified copy, injected ENOSPC and cancellation while
  staging. No original is replaced without a valid recovery checkpoint.
- Real Bubblewrap workers: qpdf page selection/reordering/splitting/checking,
  Poppler text, ZIP round trip, malicious TAR/ZIP entries and pager-free manuals.
- Obsidian fixtures cover wiki, Markdown and Canvas links, recoverable batch moves
  and refusal of ambiguous references. No personal vault was changed for tests.
- One-use approvals: refusal, changed plans, expiry after restart and pause/resume.
- Browser fixtures: navigation, fixed click operations, Portuguese GET search,
  POST/password form refusal, cancellation and subsequent navigation. A regression
  test verifies that the browser survives the short-lived thread that starts it.
- Public gateway rejects private/mixed DNS, local interface addresses, IPv6
  translation/tunnel routes and file/account URLs; public destination DNS is pinned.
- Clean install, reinstall, unrelated-setting preservation, uninstall retention,
  explicit data deletion, history migration, interrupted wallet migration and
  version rollback run in disposable homes.
- [GitHub CI](https://github.com/salvatra/o-amigo/actions/runs/42924220056) passed
  unit tests, real isolated Chromium fixtures, QML load/interaction, secret scanning,
  widget packaging and compilation in a fresh Arch container. Its disposable Ubuntu
  host needs a user-namespace policy adjustment; application sandboxing stays on.

## Real API and system checks

- OpenRouter search: exact configured DeepSeek model and price caps, Parallel Fast,
  `max_uses: 1`; Wafer provider, one search, five citations, 2.695 seconds,
  API-reported USD 0.001301652.
- Installed agent: `system_info` plus final model round completed in 4.99 seconds;
  Cohere/Baidu providers, API-reported USD 0.00116199912. The original active
  conversation was restored after the synthetic acceptance conversation.
- A bounded request exposing only one server page-fetch completed in 2.308 seconds,
  Particle AI provider, API-reported USD 0.00017498. The API omitted fetch usage, so
  this confirms request compatibility, not a verified fetch count.
- Real HTTPS browser navigation, read/scroll and hashed download delivery passed.
  The browser has no personal home, key, session bus or direct host network access.
  Visible sessions persist; hidden idle sessions terminate and remove their profile.
- PackageKit resolved configured-repository packages and installed the required
  python-pycups dependency through normal authentication; exact installed version
  was checked afterwards. General upgrades/removals were never requested.
- Real CUPS inspection found the existing printer and queue; printer configuration
  and physical printing were not changed. USB/CUPS mutation checks use fixtures.

## Installed desktop, appearance and performance

- Existing key copied and verified in KWallet; SQLite history and active conversation
  migrated. The original wallet/history remain available for explicit recovery.
- Installed singleton service starts hidden, persists work while hidden and answers
  D-Bus activation. Legacy activation retirement, restoration and retirement passed.
- Native Tidal and Breeze QML checks at 200%: Enter, Shift+Enter, Esc, drafts,
  settings categories and account form. The optional widget loaded in a disposable
  Plasma environment; its D-Bus bridge and missing-service state were exercised.
- Actual KGlobalAccel F12: centered placement, focus and previous-window restoration.
  Physical Wayland pointer: 96px boundary, 300ms dwell, leave cancellation and
  open-only behavior. Home/Work desktop routing passed with original names restored.
- Warm open: 34.09 ms; frame geometry 304,34,832,592 on a 1440x900 logical output,
  below its 30px panel. The content area is 800x560; Plasma adds its frame margins.
- Settings and separate browser passed restored, maximized, partial-maximized and
  fullscreen Tidal window-control checks. Native frames return on restoration;
  full maximization uses the existing panel controls. No panel button was added.
- Eight-second hidden-idle sample: 0.0% of one CPU core, 127.02 MiB proportional
  resident memory (242.52 MiB RSS including shared Qt libraries). This is a local
  measurement, not a performance guarantee for other systems. No idle browser
  remains resident after its 90-second timeout.
- Private Tidal integration: 127 tests, allowlisted capture, no-drift verification
  and a second capture with no changes. Restore of 187 captured files into a
  disposable home preserved private/unknown JSON fields; repeat restore changed 0.

The standalone popup uses `PlasmaCore.Dialog` with a utility-window role, retaining
Plasma background/blur/slide behavior while allowing independent positioning. The
AppletPopup role ignored absolute positioning outside a panel containment. The
optional widget uses Plasma's own containment popup.

## Limits of this evidence

- One physical monitor was available. Additional output coordinates are simulated;
  this is not a claim of testing real mixed-DPI or multi-monitor hardware.
- No removable drive was available. UDisks mount/unmount/eject and device identity
  changes are tested against service fixtures, not a real USB/Ventoy device.
- CUPS discovery is real; configuration, queue changes and job submission are fixture
  tested. Successful submission would still not prove that paper was printed.
- Not every third-party website is supported. Browser operations deliberately refuse
  authenticated accounts, publication, purchases and non-search form submission.
- Obsidian plugins with nonstandard link formats are not rewritten automatically;
  ambiguous native references are refused rather than guessed.
- No full reboot was performed during this live desktop session. Background start,
  restart, singleton, D-Bus and installed autostart files were checked separately.

Keys, personal conversations, screenshots of real data and runtime journals are
not included in this repository or release assets. Source scans run before pushes.

## 0.1.1 — 2026-11-11

Each popup opening starts a fresh conversation; previous messages and drafts stay
in history. Re-activating an already visible popup preserves its current chat.
The default shortcut is now Super+F12 (`Meta+F12` in KDE configuration). Running
tasks remain attached to the original conversation and are accessible through
history or the progress button; they are neither cancelled nor moved to the new
conversation. A second task is still blocked until the first finishes.

88 automated tests pass, including new conversation lifecycle/in-flight ownership
checks. The QML interaction check covers a fresh composer after reopening, retained
history/drafts, and activation without resetting an already visible conversation.
