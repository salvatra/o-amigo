#!/usr/bin/env python3
"""Build a versioned source archive, widget and checksum-pinned Arch recipe."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.build_widget import build as build_widget

ROOT=Path(__file__).resolve().parents[1]
DEPENDS=['python','python-pyqt6','python-pyqt6-webengine','python-dbus','python-gobject','python-pycups',
         'qt6-declarative','kirigami','libplasma','kdeplasma-addons','kconfig','kglobalaccel','libsecret','bubblewrap',
         'qpdf','poppler','man-db','udisks2','cups','cups-pk-helper','packagekit','usbutils','fontconfig']

def build(version,allow_dirty=False):
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:[a-z0-9.]*)?',version):raise ValueError('Invalid version')
    status=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)
    if status and not allow_dirty:raise RuntimeError('Commit the tested source before building a release.')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    destination=ROOT/'dist'/version;destination.mkdir(parents=True,exist_ok=True)
    archive=destination/f'o-amigo-{version}.tar.gz'
    tar=subprocess.check_output(['git','archive','--format=tar',f'--prefix=o-amigo-{version}/','HEAD'],cwd=ROOT)
    archive.write_bytes(gzip.compress(tar,mtime=0));sha=hashlib.sha256(archive.read_bytes()).hexdigest()
    # The source archive contains only committed public files; private runtime data
    # lives outside this tree. The recipe verifies the release asset's exact hash.
    recipe=f'''pkgname=o-amigo
pkgver={version}
pkgrel=1
pkgdesc='Native KDE Plasma assistant with isolated tools and OpenRouter'
arch=('any')
url='https://github.com/salvatra/o-amigo'
license=('MIT')
depends=({' '.join(repr(p) for p in DEPENDS)})
makedepends=('python')
source=("https://github.com/salvatra/o-amigo/releases/download/v$pkgver/o-amigo-$pkgver.tar.gz")
sha256sums=('{sha}')

build() {{
    cd "$srcdir/o-amigo-$pkgver"
    python scripts/build_widget.py
}}

check() {{
    cd "$srcdir/o-amigo-$pkgver"
    python -m unittest discover -s tests -q
}}

package() {{
    cd "$srcdir/o-amigo-$pkgver"
    install -dm755 "$pkgdir/usr/lib/o-amigo/quickask" "$pkgdir/usr/bin"
    cp -r amigo qml kwin scripts "$pkgdir/usr/lib/o-amigo/"
    install -m644 quickask/__init__.py quickask/core.py quickask/vault.py "$pkgdir/usr/lib/o-amigo/quickask/"
    install -m644 LICENSE THIRD_PARTY.md SOURCE_REVISION "$pkgdir/usr/lib/o-amigo/"
    install -m755 packaging/o-amigo packaging/o-amigo-integrate "$pkgdir/usr/bin/"
    install -Dm644 packaging/org.kde.oamigo.desktop "$pkgdir/usr/share/applications/org.kde.oamigo.desktop"
    install -Dm644 LICENSE "$pkgdir/usr/share/licenses/o-amigo/LICENSE"
    install -Dm644 THIRD_PARTY.md "$pkgdir/usr/share/doc/o-amigo/THIRD_PARTY.md"
    install -Dm644 README.md "$pkgdir/usr/share/doc/o-amigo/README.md"
    install -dm755 "$pkgdir/usr/share/plasma/plasmoids/org.kde.oamigo"
    python -m zipfile -e dist/o-amigo.plasmoid "$pkgdir/usr/share/plasma/plasmoids/org.kde.oamigo"
    find "$pkgdir" -type d -name __pycache__ -prune -exec rm -rf '{{}}' +
}}
'''
    (destination/'PKGBUILD').write_text(recipe)
    build_widget(ROOT/'dist/o-amigo.plasmoid');shutil.copyfile(ROOT/'dist/o-amigo.plasmoid',destination/'o-amigo.plasmoid')
    (destination/'release.json').write_text(json.dumps({'version':version,'commit':commit,'source_sha256':sha},indent=2))
    return destination

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--version',default='0.1.1');parser.add_argument('--allow-dirty',action='store_true');parser.add_argument('--build-arch',action='store_true');args=parser.parse_args()
    target=build(args.version,args.allow_dirty)
    if args.build_arch:subprocess.run(['makepkg','--nodeps','--cleanbuild','--force'],cwd=target,check=True)
    print(target)
if __name__=='__main__':main()
