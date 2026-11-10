"""Small, read-only system facts. No command text or environment dump capability."""
import os
from pathlib import Path
import platform
import shutil
from .policy import Denied
from .sandbox import Sandbox

class System:
    def __init__(self,policy,cancel=None):self.policy=policy;self.cancel=cancel
    def info(self,section):
        if section=='os':return {'kernel':platform.release(),'architecture':platform.machine(),'distribution':platform.freedesktop_os_release().get('PRETTY_NAME','Linux')}
        if section=='memory':
            fields={'MemTotal','MemAvailable','SwapTotal','SwapFree'};result={}
            for line in Path('/proc/meminfo').read_text().splitlines():
                key,_,value=line.partition(':')
                if key in fields:result[key]=int(value.strip().split()[0])*1024
            return {'bytes':result}
        if section=='cpu':
            model=next((line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')),'Unknown')
            return {'model':model,'logical_cpus':os.cpu_count(),'load_1_5_15_minutes':list(os.getloadavg())}
        if section=='storage':
            result=[]
            for path in self.policy.roots:
                try:usage=shutil.disk_usage(path)
                except OSError:continue
                result.append({'authorized_folder':str(path),'total_bytes':usage.total,'free_bytes':usage.free})
            return result
        if section=='session':return {key:os.environ.get(key,'') for key in ('XDG_CURRENT_DESKTOP','XDG_SESSION_TYPE','LANG')}
        raise Denied('Secção de informação do sistema desconhecida.')
    def command(self,variant):
        variants={'kernel':('uname',['-srmo']),'usb_hardware':('lsusb',[])}
        if variant not in variants:raise Denied('Variante de comando não autorizada.')
        command,args=variants[variant]
        return Sandbox().run(command,args,cancel=self.cancel)
