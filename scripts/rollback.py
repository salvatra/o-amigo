#!/usr/bin/env python3
"""Switch back to the previous installed code version, retaining private data."""
import argparse
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.install import Install

def rollback(i):
    previous=i.root/'previous';current=i.root/'current'
    if not previous.is_symlink() or not previous.resolve().is_dir():raise RuntimeError('Não existe uma versão anterior instalada.')
    target=previous.resolve();old=current.resolve();temporary=i.root/'.rollback-new'
    if not target.is_relative_to(i.root/'releases'):raise RuntimeError('A versão anterior não pertence às versões instaladas.')
    temporary.unlink(missing_ok=True);temporary.symlink_to(target);os.replace(temporary,current)
    previous.unlink();previous.symlink_to(old);i.artifacts()
    if i.activate:i.start()
    return target.name

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--home',type=Path);parser.add_argument('--no-activate',action='store_true');args=parser.parse_args()
    if args.home and not args.no_activate:parser.error('--home requires --no-activate')
    print('Versão restaurada:',rollback(Install(args.home,not args.no_activate)))
if __name__=='__main__':main()
