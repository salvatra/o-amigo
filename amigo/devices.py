"""Selected removable filesystems through UDisks2; no block-device writes."""
import hashlib
import os
from pathlib import Path
from .policy import Denied
from .transactions import Cancelled

SERVICE='org.freedesktop.UDisks2'
BASE='/org/freedesktop/UDisks2'
BLOCK=SERVICE+'.Block';DRIVE=SERVICE+'.Drive';FS=SERVICE+'.Filesystem'

def cstring(value):return bytes(value).rstrip(b'\0').decode('utf-8',errors='replace')

class SystemBus:
    def __init__(self):
        import dbus
        self.dbus=dbus;self.bus=dbus.SystemBus(private=True)
    def objects(self):return self.dbus.Interface(self.bus.get_object(SERVICE,BASE),'org.freedesktop.DBus.ObjectManager').GetManagedObjects(timeout=15)
    def action(self,path,interface,method):
        if method not in {FS:('Mount','Unmount'),DRIVE:('PowerOff','Eject')}.get(interface,()):raise Denied('Unknown device operation')
        options={'options':'nosuid,nodev'} if method=='Mount' else {}
        return getattr(self.dbus.Interface(self.bus.get_object(SERVICE,path),interface),method)(self.dbus.Dictionary(options,signature='sv'),timeout=120)
    def close(self):self.bus.close()

class Devices:
    def __init__(self,selected=(),policy=None,cancel=None,backend=None):
        self.selected=frozenset(selected);self.policy=policy;self.cancel=cancel;self.backend=backend
    def api(self):
        if self.backend is None:self.backend=SystemBus()
        return self.backend
    def inventory(self):
        objects=self.api().objects();result=[]
        for path,interfaces in objects.items():
            block=interfaces.get(BLOCK,{});drive_path=str(block.get('Drive','/'));drive=objects.get(drive_path,{}).get(DRIVE,{})
            if not block or FS not in interfaces or not drive or block.get('HintSystem') or block.get('IdUsage')!='filesystem':continue
            if not (drive.get('ConnectionBus')=='usb' or drive.get('Removable')):continue
            uuid=str(block.get('IdUUID',''));drive_id=str(drive.get('Id','') or drive.get('Serial',''))
            if not uuid or not drive_id:continue
            identity=hashlib.sha256((drive_id+'\0'+uuid).encode()).hexdigest()[:32]
            mounts=[cstring(v) for v in interfaces[FS].get('MountPoints',[])]
            result.append({'id':identity,'uuid':uuid,'label':str(block.get('IdLabel','')),'model':str(drive.get('Model','')),
                           'bytes':int(block.get('Size',0)),'filesystem':str(block.get('IdType','')),'mountpoints':mounts,
                           'selected':identity in self.selected,'object':str(path),'drive':drive_path,
                           'can_power_off':bool(drive.get('CanPowerOff')),'ejectable':bool(drive.get('Ejectable')),
                           'siblings':str(drive.get('SiblingId',''))})
        return result
    def identify(self):
        return [{k:v for k,v in item.items() if k not in ('object','drive','siblings')} for item in self.inventory()]
    def choose(self,identifier):
        matches=[item for item in self.inventory() if item['id']==identifier]
        if len(matches)!=1:raise Denied('Unidade ausente ou identidade ambígua.')
        if identifier not in self.selected:raise Denied('Seleciona esta unidade nas definições antes de permitir operações.')
        if self.cancel and self.cancel.is_set():raise Cancelled('Operação cancelada.')
        return matches[0]
    def authorized_mounts(self):
        # Restrict removable grants to private desktop mount directories. A device
        # mounted over /home, /etc or an arbitrary fstab target cannot expand access.
        roots=[];base=Path('/run/media')/os.environ.get('USER',str(os.getuid()))
        for item in self.inventory():
            if item['selected']:
                for value in item['mountpoints']:
                    path=Path(value)
                    if path.is_absolute() and path.is_relative_to(base) and path!=base and not path.is_symlink():roots.append(path)
        return roots
    def mount(self,identifier):
        item=self.choose(identifier)
        if not item['mountpoints']:self.api().action(item['object'],FS,'Mount')
        fresh=self.choose(identifier)
        if not fresh['mountpoints']:raise RuntimeError('A montagem não foi confirmada.')
        return {'verified':True,'device':{k:v for k,v in fresh.items() if k not in ('object','drive','siblings')}}
    def unmount(self,identifier):
        item=self.choose(identifier)
        if item['mountpoints']:self.api().action(item['object'],FS,'Unmount')
        if self.choose(identifier)['mountpoints']:raise RuntimeError('A desmontagem não foi confirmada.')
        return {'verified':True,'unmounted':identifier}
    def eject(self,identifier):
        item=self.choose(identifier);affected=[v for v in self.inventory() if v['drive']==item['drive'] or item['siblings'] and v['siblings']==item['siblings']]
        if any(v['mountpoints'] for v in affected):raise Denied('Desmonta primeiro todas as partições da unidade e dos dispositivos associados. Nunca é usada desmontagem forçada.')
        method='PowerOff' if item['can_power_off'] else 'Eject' if item['ejectable'] else None
        if not method:raise Denied('A unidade não suporta ejeção segura pelo sistema.')
        self.api().action(item['drive'],DRIVE,method)
        return {'verified':True,'safe_removal_completed':identifier,'method':method}
    def close(self):
        if self.backend:self.backend.close()
