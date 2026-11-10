from pathlib import Path
import copy
import json
import os
import tempfile

DEFAULTS = {
 'model': 'deepseek/deepseek-v4.1-flash-1017', 'input_price':0.30, 'output_price':1.20,
 'routing':'balanced', 'providers':[], 'allow_fallbacks':True,
 'simple_tokens':1024, 'tool_tokens':4096, 'thinking_tokens':4096,
 'system_prompt':'Responde em português europeu, de forma breve e clara. Explicita unidades, pressupostos e incertezas. Só afirma ter efetuado uma ação quando a ferramenta confirmar o resultado.',
 'include_time':True, 'temperature':None, 'max_rounds':16, 'max_searches':3,
 'allowed_folders':[], 'tools_enabled':False, 'web_enabled':False,
 'search_engine':'parallel', 'search_mode':'basic', 'search_results':5,
 'width':800, 'height':560, 'shortcut':'F12', 'hotspot_enabled':True,
 'hotspot_width':96, 'hotspot_delay':300, 'pinned':False,
 'backup_days':7, 'backup_bytes':2147483648, 'browser_idle_seconds':90,
}

def validate(value):
    if not isinstance(value,dict) or set(value)-set(DEFAULTS):
        raise ValueError('Unknown settings')
    result = copy.deepcopy(DEFAULTS); result.update(value)
    for key in ('simple_tokens','tool_tokens','thinking_tokens','max_rounds','max_searches',
                'width','height','hotspot_width','hotspot_delay','backup_days','backup_bytes','browser_idle_seconds','search_results'):
        if type(result[key]) is not int or result[key]<1: raise ValueError('Invalid '+key)
    for key in ('input_price','output_price'):
        if type(result[key]) not in (int,float) or not 0 <= result[key] < 1e6: raise ValueError('Invalid '+key)
    if not isinstance(result['allowed_folders'],list) or any(not isinstance(p,str) or not Path(p).is_absolute() for p in result['allowed_folders']):
        raise ValueError('Authorized folders must be absolute paths')
    if result['routing'] not in ('balanced','price','throughput','latency'): raise ValueError('Invalid routing')
    if not isinstance(result['model'],str) or not result['model'].strip(): raise ValueError('Missing model')
    return result

class Settings:
    def __init__(self, path):
        self.path=Path(path)
        self.value=validate(json.loads(self.path.read_text()) if self.path.exists() else {})
    def save(self,value):
        checked=validate(value)
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd,tmp=tempfile.mkstemp(dir=self.path.parent)
        try:
            with os.fdopen(fd,'w') as file: json.dump(checked,file,ensure_ascii=False,indent=2)
            os.replace(tmp,self.path)
            self.value=checked
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
