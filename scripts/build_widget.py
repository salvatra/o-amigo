#!/usr/bin/env python3
"""Build the optional widget from the shared UI, without a second source copy."""
import argparse
from pathlib import Path
import shutil
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
def build(destination):
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='o-amigo-widget-') as directory:
        staged=Path(directory)/'widget';shutil.copytree(ROOT/'widget',staged)
        shared=staged/'contents/ui/shared';shared.mkdir()
        shutil.copy2(ROOT/'qml/ChatView.qml',shared/'ChatView.qml')
        with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(staged.rglob('*')):
                if file.is_file():archive.write(file,file.relative_to(staged))
    return destination

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('destination',nargs='?',default=ROOT/'dist/o-amigo.plasmoid')
    print(build(parser.parse_args().destination))
