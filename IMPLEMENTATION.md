# Implementation map — 0.1.0

The initial release implements the accepted desktop assistant scope. This file
maps features to their maintained sources; test evidence and practical limits are
in [VALIDATION.md](VALIDATION.md).

| Area | Sources |
|---|---|
| Independent service, single instance, D-Bus activation | `amigo/app.py`, `amigo/controller.py` |
| Native popup, chat, history and categorized settings | `qml/`, `amigo/settings_ui.py`, `amigo/presentation.py` |
| F12, exact top-center hover region, focus restoration | `kwin/`, `amigo/integration.py` |
| Optional widget sharing the chat UI | `widget/`, `scripts/build_widget.py` |
| Exact model, capped routing, streamed tool calls and citations | `amigo/protocol.py`, `amigo/network.py` |
| Durable bounded agent, approval and continuation | `amigo/agent.py`, `amigo/approval.py`, `amigo/history.py` |
| Validated catalogue, paths, exclusions and isolated workers | `amigo/tools.py`, `amigo/schema.py`, `amigo/policy.py`, `amigo/sandbox.py` |
| Recoverable files, hashes, dates and conflict handling | `amigo/files.py`, `amigo/transactions.py` |
| PDF, archives and link-aware Obsidian operations | `amigo/documents.py`, `amigo/archive_worker.py`, `amigo/obsidian.py` |
| Typed USB, CUPS, PackageKit and fixed diagnostics | `amigo/devices.py`, `amigo/printers.py`, `amigo/packages.py`, `amigo/system.py` |
| Ephemeral Chromium, controlled public gateway | `amigo/browser.py`, `amigo/browser_worker.py`, `amigo/web_proxy.py`, `amigo/web_policy.py` |
| User-local install, migration, rollback and removal | `scripts/install.py`, `amigo/migration.py`, `scripts/rollback.py`, `scripts/legacy.py`, `scripts/uninstall.py` |
| Source/widget/Arch release artefacts | `scripts/build_release.py`, `packaging/` |

There is no arbitrary terminal/Python capability, model-accessible policy editor,
root session, AUR/general-update operation, partition/format operation, personal
browser profile, account automation, publishing or purchasing capability. Public
defaults grant no personal folders and keep optional tools disabled until chosen.
The private Tidal repository contains its own preferences, capture allowlist and
an exact public commit pin; it does not fork the application sources.
