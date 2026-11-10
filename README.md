# O Amigo

Native KDE Plasma assistant under development. **This repository is not yet an
installable replacement for Quick Ask.** The current installed application is
intentionally preserved until migration and security checks are complete.

## Implemented foundation

- Original MIT-licensed, credential-free Quick Ask client.
- Closed, structured capability registry for authorized file reads, metadata,
  SHA-256, installed manuals, and PDF inspection/text extraction.
- Filesystem policy rejecting protected locations, symlinks, hard links,
  traversal, special files and unauthorized commands.
- Bubblewrap execution without network, inherited credentials or session D-Bus.
- Atomic settings storage and a native Plasma/Kirigami presentation preview.

Writes, administrative actions, agent loops, web search and the isolated browser
are **not enabled**. The preview explicitly identifies itself as development UI.
No API key, conversation database, user profile or personal configuration is
included in this repository.

## Development

Requires Python 3, PyQt6, Plasma QML components, Kirigami and Bubblewrap. Optional
read-only tools use system `man`, Poppler and qpdf.

```sh
python3 -m unittest discover -s tests -v
python3 -m amigo.presentation
```

The preview uses separate configuration and does not migrate or read the existing
key or conversation history. Existing Quick Ask source is retained in `quickask/`
as the migration foundation, not as a second installed service.

## Delivery status

See [IMPLEMENTATION.md](IMPLEMENTATION.md). Public release packages and the KDE
Store listing are not available yet. The planned initial distribution targets
Arch Linux / Plasma 6, with an optional widget and a separate local service.
