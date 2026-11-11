# Third-party components

O Amigo's own source remains under the MIT license in `LICENSE`. Runtime
components are installed separately from Arch repositories; this source release
does not bundle Qt, Chromium, KDE, fonts or their binary libraries.

| Component | Upstream license / notice |
| --- | --- |
| Python | Python Software Foundation License |
| PyQt6 and PyQt6-WebEngine | GPLv3 or Riverbank commercial license |
| Qt 6 / Qt Quick | LGPLv3, GPLv3 or Qt commercial license, depending on component |
| Qt WebEngine / Chromium | Qt licensing plus Chromium's third-party notices |
| KDE Plasma / Kirigami | LGPL family; consult the installed component's notices |
| markdown-it-py / mdurl | MIT |
| KSyntaxHighlighting | MIT; syntax definitions and themes have their own notices |
| Bubblewrap | LGPL-2.1-or-later |
| PackageKit | GPL-2.0-or-later |
| python-pycups | GPL-2.0-or-later |
| CUPS, UDisks2, Polkit, Secret Service, qpdf, Poppler, libsecret | Separate system dependencies under their respective upstream licenses |

If redistributing a combined binary distribution, comply with the licenses of
all components, including the GPL obligations of the PyQt bindings. The MIT
license on the application's own code does not replace those obligations.

The browser copies only the selected local UI fonts into a private, ephemeral
runtime directory so it can match the desktop. Those fonts are never included
in a repository, release archive or widget. Their licenses remain with their
respective owners.

Primary licensing references:

- [Riverbank PyQt licensing](https://www.riverbankcomputing.com/commercial/license-faq)
- [Qt licensing](https://doc.qt.io/qt-6/licensing.html)
- [Qt WebEngine licensing and third-party notices](https://doc.qt.io/qt-6/qtwebengine-licensing.html)
- [KDE licensing policy](https://community.kde.org/Policies/Licensing_Policy)

The OpenRouter API is an external paid service, not bundled software. Users
provide their own credentials and accept that service's applicable terms.
