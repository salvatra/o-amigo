#!/usr/bin/env python3
"""Remove only O Amigo integration; keep history and key unless explicitly selected."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.install import Install,run,write
from amigo.migration import secret

ACTIONS=('O Amigo Toggle','O Amigo Focus','O Amigo Restore Focus','O Amigo Reload')

def remove_group(path,group):
    if not path.exists():return
    keep=[];skip=False
    for line in path.read_text().splitlines(keepends=True):
        if line.startswith('['):skip=line.strip()=='['+group+']'
        if not skip:keep.append(line)
    write(path,''.join(keep))

def uninstall(installation,delete_history=False,delete_key=False):
    i=installation
    # Remove activation before quitting, so hover/shortcut cannot restart it.
    for path in (i.data/'dbus-1/services/org.kde.OAmigo.service',i.config/'autostart/org.kde.oamigo.desktop'):path.unlink(missing_ok=True)
    if i.activate:
        run('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.unloadScript','o-amigo',check=False)
        if i.has_owner():
            run('qdbus6','org.kde.OAmigo','/OAmigo','org.kde.OAmigo.Quit')
            deadline=time.monotonic()+10
            while i.has_owner() and time.monotonic()<deadline:time.sleep(.05)
            if i.has_owner():raise RuntimeError('A aplicação ainda está a terminar uma operação. Os dados e o código foram conservados; volta a desinstalar depois de terminar.')
    i.cfg('kwinrc','Plugins','o-amigoEnabled',None)
    order=i.readcfg('kwinrulesrc','General','Order')
    i.cfg('kwinrulesrc','General','Order',','.join(v for v in order.split(',') if v and v!='o-amigo-popup'))
    remove_group(i.config/'kwinrulesrc','o-amigo-popup')
    for name in ACTIONS:
        if i.activate:run('qdbus6','org.kde.kglobalaccel','/kglobalaccel','org.kde.KGlobalAccel.unregister','kwin',name,check=False)
        i.cfg('kglobalshortcutsrc','kwin',name,None)
    for path in (i.launcher,i.data/'applications/org.kde.oamigo.desktop'):path.unlink(missing_ok=True)
    widget=i.data/'plasma/plasmoids/org.kde.oamigo'
    for path in (i.data/'kwin/scripts/o-amigo',widget):
        if path.is_dir():shutil.rmtree(path)
    for link in ('current','previous'):(i.root/link).unlink(missing_ok=True)
    if (i.root/'releases').is_dir():shutil.rmtree(i.root/'releases')
    if delete_key:
        ok,_=secret('clear','o-amigo')
        if not ok:raise RuntimeError('A integração foi removida mas o KWallet não confirmou a remoção da chave.')
    if delete_history and i.root.exists():shutil.rmtree(i.root)
    elif i.root.exists():write(i.root/'installation.json',json.dumps({'installed':False,'history_retained':True,'key_retained':not delete_key}))
    if i.activate:
        run('qdbus6','org.kde.KWin','/KWin','org.kde.KWin.reconfigure',check=False)
        run('kbuildsycoca6','--noincremental',check=False)
    return {'integration_removed':True,'history_retained':not delete_history,'key_retained':not delete_key}

def main():
    os.umask(0o077);parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home',type=Path);parser.add_argument('--no-activate',action='store_true')
    parser.add_argument('--delete-history',action='store_true');parser.add_argument('--delete-key',action='store_true')
    args=parser.parse_args()
    if args.home and (not args.no_activate or args.delete_key):parser.error('Disposable roots require --no-activate and cannot delete a real key.')
    print(json.dumps(uninstall(Install(args.home,not args.no_activate),args.delete_history,args.delete_key)))

if __name__=='__main__':main()
