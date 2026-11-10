# Implementation status

This file reports implemented behavior, not a claim that the full accepted plan
has been delivered.

## Completed

- Public source repository and incremental commits.
- Import of the existing client without credentials or user data.
- Enforced path policy and closed read-only capability registry.
- Bubblewrap wrapper with a minimal filesystem, clean environment and no network.
- Tests for protected paths, links, command injection and unexpected arguments.
- Native Plasma popup preview and independently stored preview settings.
- Atomic file edits, verified copies/moves, timestamps, desktop Trash and directory creation.
- Durable recovery journal with quota/retention, undo conflicts and crash interruption state.
- Structured streaming tool-call assembly and exact provider price policy.
- PDF page selection/reordering/merging/splitting in Bubblewrap, with output verification.
- ZIP/TAR inspection/extraction and ZIP creation, with traversal/link/size checks.
- Obsidian note/attachment moves updating native wiki, Markdown and Canvas references in a recoverable batch.
- 38 automated tests, including real sandboxed PDF/archive execution and adversarial fixtures.

## Required before migration or release

- Production service, D-Bus lifecycle, F12 and top-center activation.
- Full settings pages, history UI and shared optional widget frontend.
- Tool-call streaming, durable agent loop and round/search budgets.
- Recovery interface and broader concurrent-change/cancellation coverage.
- Device, CUPS and approved package-install adapters.
- OpenRouter search and isolated browser with controlled network proxy.
- Broader adversarial tests, cancellation and crash recovery tests.
- Live theme/focus/performance verification and settings-window integration.
- Packaging, migration, uninstall/rollback and actual dependency installation.
- Tidal capture/restore integration and pinned tested release.

Do not publish a stable release or replace the working Quick Ask installation
until these requirements are verified.
