#!/usr/bin/env python3
"""Retire/recover legacy activation only after the new migration is validated."""
import argparse
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.install import Install,run,write

FILES=(('data','dbus-1/services/local.quickask.service'),('config','autostart/local.quickask.desktop'))

def retire(i):
    if not i.has_owner():raise RuntimeError('O Amigo tem de estar operacional antes de retirar a integração antiga.')
    state=json.loads(run('qdbus6','org.kde.OAmigo','/OAmigo','org.kde.OAmigo.State'))
    marker=i.root/'migration.json'
    if not state.get('validated') or not marker.exists():raise RuntimeError('A ligação e a migração novas ainda não estão validadas.')
    migration=json.loads(marker.read_text())
    if migration.get('history')!='copied' or migration.get('key') not in ('copied-and-verified','existing'):raise RuntimeError('A migração antiga ainda não está completa.')
    backup=i.root/'legacy-activation';backup.mkdir(exist_ok=True,mode=0o700)
    if not (backup/'state.json').exists():
        write(backup/'state.json',json.dumps({'enabled':i.readcfg('kwinrc','Plugins','quick-askEnabled')}))
        for base,relative in FILES:
            source=getattr(i,base)/relative
            if source.exists():
                target=backup/base/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    for base,relative in FILES:(getattr(i,base)/relative).unlink(missing_ok=True)
    run('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.unloadScript','quick-ask',check=False)
    i.cfg('kwinrc','Plugins','quick-askEnabled','false')
    run('qdbus6','local.quickask','/QuickAsk','local.quickask.Quit',check=False)
    # Preserve old code, launcher, history, wallet item and rule for explicit recovery.
    return {'legacy_activation':'retired','legacy_data':'preserved'}

def restore(i):
    backup=i.root/'legacy-activation'
    if not (backup/'state.json').exists():raise RuntimeError('Não existe uma cópia da ativação antiga.')
    for base,relative in FILES:
        source=backup/base/relative
        if source.exists():write(getattr(i,base)/relative,source.read_text())
    state=json.loads((backup/'state.json').read_text());i.cfg('kwinrc','Plugins','quick-askEnabled',state['enabled'] or 'true')
    run('qdbus6','org.kde.KWin','/KWin','org.kde.KWin.reconfigure')
    run('qdbus6','local.quickask','/QuickAsk','local.quickask.Show')
    return {'legacy_activation':'restored'}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('retire','restore'));args=parser.parse_args()
    print(json.dumps(retire(Install()) if args.action=='retire' else restore(Install())))
if __name__=='__main__':main()
