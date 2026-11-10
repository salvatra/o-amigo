from pathlib import Path
import copy
import json
import os
import tempfile
import math

DEFAULTS = {
 'model': 'deepseek/deepseek-v4.1-flash-1017', 'input_price':0.30, 'output_price':1.20,
 'routing':'balanced', 'providers':[], 'provider_mode':'preferred', 'ignored_providers':[], 'allow_fallbacks':True,
 'simple_tokens':1024, 'tool_tokens':4096, 'thinking_tokens':4096,
 'system_prompt':'Responde em português europeu, de forma breve e clara. Explicita unidades, pressupostos e incertezas. Só afirma ter efetuado uma ação quando a ferramenta confirmar o resultado.',
 'include_time':True, 'temperature':None, 'top_p':None, 'top_k':None, 'min_p':None,
 'frequency_penalty':None, 'presence_penalty':None, 'repetition_penalty':None, 'seed':None, 'stop':[], 'reasoning_effort':'auto', 'max_rounds':16, 'max_searches':3, 'max_fetches':6,
 'language':'pt-PT', 'conciseness':'brief',
 'allowed_folders':[], 'tools_enabled':False, 'web_enabled':False,
 'protected_folders':[], 'allowed_removable':[], 'allowed_devices':[], 'disabled_tools':[],
 'search_engine':'parallel', 'search_mode':'auto', 'search_results':5,
 'allowed_domains':[], 'excluded_domains':[], 'browser_enabled':False,
 'width':800, 'height':560, 'shortcut':'F12', 'hotspot_enabled':True,
 'hotspot_width':96, 'hotspot_delay':300, 'pinned':False,
 'backup_days':7, 'backup_bytes':2147483648, 'browser_idle_seconds':90,
 'animations':True, 'notifications':True,
}

def validate(value):
    if not isinstance(value,dict) or set(value)-set(DEFAULTS):
        raise ValueError('Unknown settings')
    result = copy.deepcopy(DEFAULTS); result.update(value)
    ranges={'simple_tokens':(64,131072),'tool_tokens':(128,131072),'thinking_tokens':(128,131072),
            'max_rounds':(1,100),'max_searches':(0,30),'max_fetches':(0,30),'width':(420,1600),'height':(300,1200),
            'hotspot_width':(16,512),'hotspot_delay':(150,3000),'backup_days':(1,365),
            'backup_bytes':(1024**2,1024**4),'browser_idle_seconds':(15,3600),'search_results':(1,10)}
    for key,(minimum,maximum) in ranges.items():
        if type(result[key]) is not int or not minimum<=result[key]<=maximum:raise ValueError('Invalid '+key)
    for key in ('allow_fallbacks','include_time','tools_enabled','web_enabled','browser_enabled','hotspot_enabled','pinned','animations','notifications'):
        if type(result[key])is not bool:raise ValueError('Invalid '+key)
    for key in ('input_price','output_price'):
        if type(result[key]) not in (int,float) or not 0 <= result[key] < 1e6: raise ValueError('Invalid '+key)
    for key in ('allowed_folders','protected_folders','allowed_removable','allowed_devices','providers','ignored_providers','allowed_domains','excluded_domains','disabled_tools','stop'):
        if not isinstance(result[key],list) or len(result[key])>100 or any(not isinstance(p,str) or not p or len(p)>4096 or '\x00' in p for p in result[key]):
            raise ValueError('Invalid '+key)
    for key in ('allowed_folders','protected_folders','allowed_removable'):
        if any(not Path(p).is_absolute() for p in result[key]):raise ValueError('Folders must be absolute paths')
    if result['allowed_domains'] and result['excluded_domains']:raise ValueError('Choose either allowed or excluded domains')
    if result['routing'] not in ('balanced','price','throughput','latency'): raise ValueError('Invalid routing')
    if result['provider_mode'] not in ('preferred','only'):raise ValueError('Invalid provider mode')
    if result['search_engine'] not in ('parallel','exa','perplexity','firecrawl'):raise ValueError('Use an engine that enforces server search limits')
    if result['search_mode'] not in ('auto','fast','basic','advanced','turbo','instant','deep-lite','deep','deep-reasoning'):raise ValueError('Invalid search mode')
    if result['reasoning_effort'] not in ('auto','low','medium','high'):raise ValueError('Invalid reasoning effort')
    for key,minimum,maximum in (('top_k',1,1000),('seed',0,2147483647)):
        if result[key] is not None and (type(result[key]) is not int or not minimum<=result[key]<=maximum):raise ValueError('Invalid '+key)
    for key,minimum,maximum in (('min_p',0,1),('frequency_penalty',-2,2),('presence_penalty',-2,2),('repetition_penalty',0.1,2)):
        if result[key] is not None and (type(result[key]) not in (int,float) or not math.isfinite(result[key]) or not minimum<=result[key]<=maximum):raise ValueError('Invalid '+key)
    if len(result['stop'])>4 or any(len(v)>256 for v in result['stop']):raise ValueError('Invalid stop sequences')
    for key,maximum in (('temperature',2),('top_p',1)):
        if result[key] is not None and (type(result[key])not in(int,float) or not math.isfinite(result[key]) or not 0<=result[key]<=maximum):raise ValueError('Invalid '+key)
    for key in ('system_prompt','shortcut','language','conciseness'):
        if not isinstance(result[key],str) or '\x00' in result[key] or len(result[key])>32768:raise ValueError('Invalid '+key)
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
