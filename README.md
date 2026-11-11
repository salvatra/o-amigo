# O Amigo

A native KDE Plasma assistant with an independent local service, a themed popup,
an optional Plasma widget and OpenRouter. Initial target: Arch Linux with Plasma 6.
Version **0.2.2** keeps response scrolling fully manual; tested behavior and hardware
limitations are recorded in [VALIDATION.md](VALIDATION.md). It is not published on
KDE Store. [Guia rápido em português](UTILIZACAO.md).

## Install on Arch / Plasma

Install dependencies from the configured repositories:

```sh
sudo pacman -S --needed python python-markdown-it-py syntax-highlighting python-pyqt6 python-pyqt6-webengine python-dbus \
  python-gobject python-pycups qt6-declarative kirigami libplasma kdeplasma-addons \
  kconfig kglobalaccel libsecret bubblewrap qpdf poppler man-db udisks2 cups \
  cups-pk-helper packagekit usbutils fontconfig
```

Use a normally maintained Arch installation; the installer does not refresh the
system package database or perform an automatic general upgrade.

From a checked-out source tree, as your normal desktop user:

```sh
python scripts/install.py
```

This installs versioned code under `~/.local/share/o-amigo/releases`, a launcher,
D-Bus activation, KDE autostart, one KWin script and one popup-specific window
rule. Existing shortcuts and other hot corners are preserved. A conflicting
shortcut is reported rather than reassigned. No button is added to the panel.

Open **O Amigo** from the menu or press **Super+F12**. Paste an OpenRouter key and select
**Guardar e testar**. The key is stored in the desktop's unlocked Secret Service
(KWallet on KDE). Choose authorized folders and enable desired capabilities in
the settings window. Public defaults disable local tools, web search and browser
access until explicitly enabled; no personal folder is authorized by default.

The optional widget is built from the same chat interface:

```sh
python scripts/build_widget.py
kpackagetool6 --type Plasma/Applet --install dist/o-amigo.plasmoid
```

Add it through Plasma's widget chooser only if wanted. It requires the separately
installed service and explains that requirement when the service is absent.
Installing the widget alone does not grant tools or store a key in plasmashell.

## Use

- Super+F12 shows/hides the popup. The middle 96 logical pixels of the top edge open it
  after a 300 ms dwell; leaving the region cancels the pending opening.
- Reopening keeps the current conversation when there is unsent text. With an
  empty composer, opening starts a new conversation. Earlier messages and
  drafts in conversations already sent stay in history. A new conversation is
  saved only when its first message is sent; opening the popup or typing alone
  does not add a history entry. A running task continues in its original conversation;
  **Ver progresso** returns to it, and another task can start once it finishes.
- Enter sends; Shift+Enter inserts a line; Esc hides; Ctrl+N starts a conversation.
- The prompt is above the answer, with integrated send/stop and reasoning controls.
  Empty chats have no welcome copy or permanent footer; progress and costs appear
  only for a task. **Ir para o fim** jumps to the bottom only when clicked.
  Native Markdown has comfortable spacing,
  proportional headings, nested lists, quotes, syntax-highlighted code with
  **Copiar código**, and tables that scroll horizontally when needed. Select text
  per block; **Copiar resposta** copies the complete original Markdown.
  The reading position stays under your control during and after generation,
  including when more messages arrive. Jumping to the bottom never enables following.
  Hiding preserves drafts and active work; installation hands unsent text to the
  new process without creating an empty history entry.
- Responses never load a browser, remote images or model-supplied HTML. Images
  appear as alternative text; HTML is displayed literally. Only generated inline
  rich text is rendered. Links open only on activation (HTTP/HTTPS). Unknown code
  languages remain monospace. LaTeX and Mermaid are not rendered.
- Pinning keeps the popup open on outside clicks. The gear opens a normal KDE
  settings window. **Ver browser** reveals the separate isolated browser.
- One task runs at a time. **Interromper** requests cancellation. A privileged
  system transaction already committing may finish despite cancellation; it is
  never silently repeated. **Continuar** grants another bounded execution stage.

Default model: `deepseek/deepseek-v4.1-flash-1017`, reasoning disabled, balanced
provider selection, fallback allowed only within USD 0.30/M input and 1.20/M
output. There is no automatic model replacement or price increase. Defaults are
1,024 simple-response tokens and 4,096 with tools or **Pensar mais**, 16 model
rounds, three searches and six page fetches per stage. Settings expose those
limits, provider preferences, instructions, permissions and interface behavior.
Only API-reported costs are presented as known costs; missing usage is not
silently estimated. Unknown server-tool usage conservatively consumes its
reserved budget. Searches use OpenRouter credits; server page extraction is
preferred to a browser when possible.

## Capabilities and boundaries

The model chooses from a fixed, schema-validated catalogue. It cannot run a shell,
Python, arbitrary commands, change its own permissions or approve its actions.

- Files: bounded search/read, recoverable create/edit/move/copy/trash, SHA-256 and
  explicit-timezone mtime/atime changes. No promise to alter ctime or birth time.
- Documents: isolated qpdf/Poppler and ZIP/TAR operations, validated extraction,
  verified output before replacement. Obsidian moves rewrite native wiki,
  Markdown and Canvas links in a recoverable batch; ambiguous links are refused.
- USB: identify and operate explicitly selected removable filesystems through
  UDisks2. No format, partition or raw block-device write. Copying to an authorized
  mounted Ventoy volume uses normal verified file copies, not a Ventoy installer.
- CUPS: inspect printers/jobs/drivers, prepare configuration and queue actions,
  submit approved PDF/text/image print jobs. Submission does not prove physical
  printing. No PPD upload or global CUPS server configuration capability.
- Packages: search/inspect configured repositories, simulate dependency changes,
  then install signed packages through PackageKit with normal system auth.
  No AUR, local package upload, removals, downgrades or general update capability.

Administrative and irreversible actions pause with concrete targets and changes.
Approvals are one-use, expire on restart and are invalidated if preparation
changes. Read/write access is checked independently of the system prompt; known
credential/config/browser/startup locations and the assistant are excluded.
Additional exclusions can be configured. A folder grant allows its eligible
content to be used as model context when a task reads it.

External document/diagnostic workers use Bubblewrap with staged inputs, clean
environments, no session D-Bus, no key and no network. Typed UDisks, CUPS and
PackageKit system services perform their own authorized operations; there is no
model-controlled root session. The separate Chromium process has an ephemeral
profile and a network namespace. Its public-only gateway rejects local/private
DNS results and pins destination addresses. Browser tools expose bounded page
reading/navigation/search/scroll/download operations, never supplied JavaScript.
Accounts, authentication, publishing and purchases are outside this version.
The hidden idle browser exits after 90 seconds. Downloads are staged and hashed
before delivery to a new authorized file.

Recovery defaults to seven days and 2 GiB. If a safe recovery copy is unavailable,
replacement is refused; free recovery capacity or adjust settings before retrying.
Undo refuses to overwrite a later user change. After a crash, uncertain operations
are shown as interrupted and are not automatically replayed.

## Data, migration and removal

Configuration: `~/.config/o-amigo/settings.json`. Private history, task journal,
recovery and installation state: `~/.local/share/o-amigo/`. The key exists only in
Secret Service and process memory. These locations are not release sources.

To migrate Quick Ask once, retaining the original until verification:

```sh
python scripts/install.py --migrate-quick-ask
# After checking the installed service, key, history and desktop integration:
python scripts/legacy.py retire
# Restore its preserved activation if needed:
python scripts/legacy.py restore
```

The migration uses SQLite backup, preserves the active conversation and copies
and verifies the wallet entry without writing the key to a file. It refuses to
overwrite an existing unrelated destination history. Reinstallation is idempotent.
An update retains the previous code version; `python scripts/rollback.py` switches
back without deleting conversations. For a schema-incompatible future release,
follow its specific migration/rollback instructions.

```sh
python scripts/uninstall.py                  # retain settings, history and key
python scripts/uninstall.py --delete-history # also delete new app data/recovery
python scripts/uninstall.py --delete-key     # also remove the new wallet entry
```

Legacy Quick Ask data/key remain independent and are not deleted by these flags.

## Development and packaging

```sh
python -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen python tests/verify_ui.py
python tests/verify_browser.py        # real HTTPS, no API key
python tests/verify_kwin.py           # temporary native integration check
python scripts/build_release.py --version 0.2.2 --build-arch
```

Release builds require committed source and produce a reproducible source archive,
a widget, a checksum-pinned Arch `PKGBUILD`, metadata and an Arch package under
`dist/<version>/`. The Arch package provides `o-amigo` and `o-amigo-integrate`;
run the latter as your normal KDE user to configure the shortcut/autostart.
The Tidal-specific profile and deployment pin belong to the separate private
`tidal-comet-desktop` repository, not this public codebase.

Own source: MIT. See [THIRD_PARTY.md](THIRD_PARTY.md) for runtime licensing and
redistribution obligations, including PyQt's GPL/commercial licensing.
