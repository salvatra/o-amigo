"""Closed registry. Read-only capabilities are shipped first; writes remain disabled."""
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from .policy import Denied
from .sandbox import Sandbox

SPECS = [
 ('list_files', 'List an authorized folder. Protected entries are omitted.', {'path':{'type':'string'}}, ['path']),
 ('read_file', 'Read a bounded UTF-8 text file in an authorized folder.', {'path':{'type':'string'}}, ['path']),
 ('file_info', 'Inspect file size and timestamps without changing them.', {'path':{'type':'string'}}, ['path']),
 ('hash_file', 'Calculate the SHA-256 of an authorized file.', {'path':{'type':'string'}}, ['path']),
 ('read_manual', 'Read an installed system manual. No commands are executed from the manual.',
  {'name':{'type':'string'},'section':{'type':'string'}}, ['name']),
 ('pdf_info', 'Inspect PDF metadata and page count.', {'path':{'type':'string'}}, ['path']),
 ('pdf_text', 'Extract PDF text (bounded output).', {'path':{'type':'string'}}, ['path']),
]

def schemas():
    return [{'type':'function','function':{'name':name,'description':description,
             'parameters':{'type':'object','properties':props,'required':required,'additionalProperties':False}}}
            for name,description,props,required in SPECS]

class Tools:
    def __init__(self, policy):
        self.policy = policy
        self.sandbox = Sandbox()

    def call(self, name, args):
        spec = next((s for s in SPECS if s[0] == name), None)
        if not spec or not isinstance(args, dict):
            raise Denied('Unknown tool')
        if set(args) - set(spec[2]) or not set(spec[3]) <= set(args):
            raise Denied('Invalid tool arguments')
        if any(not isinstance(v,str) or len(v)>4096 or '\x00' in v for v in args.values()):
            raise Denied('Invalid argument value')
        if name == 'read_manual':
            topic = args['name']; section = args.get('section','')
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+-]{0,79}', topic):
                raise Denied('Invalid manual name')
            if section and not re.fullmatch(r'[1-9][A-Za-z0-9]{0,5}', section):
                raise Denied('Invalid manual section')
            return self.sandbox.run('man', ['-P','cat',*( [section] if section else []),topic])
        path = self.policy.path(args['path'])
        if name == 'list_files':
            result = []
            for p in sorted(path.iterdir(),key=lambda p:p.name.casefold()):
                try:
                    p = self.policy.path(str(p))
                except Denied:
                    continue
                result.append({'name':p.name,'directory':p.is_dir()})
                if len(result)>=500: break
            return result
        if name == 'file_info':
            stat = path.stat()
            return {'path':str(path),'bytes':stat.st_size,'mtime':stat.st_mtime,'atime':stat.st_atime}
        if name == 'read_file':
            with self.policy.open_read(str(path)) as file:
                content = file.read(64001)
            return {'text':content[:64000].decode('utf-8',errors='replace'),'truncated':len(content)>64000}
        if name == 'hash_file':
            with self.policy.open_read(str(path)) as file:
                digest = hashlib.file_digest(file,'sha256').hexdigest()
            return {'sha256':digest}
        if name in ('pdf_info','pdf_text'):
            with tempfile.TemporaryDirectory(prefix='o-amigo-') as tmp:
                staged = Path(tmp)/'input.pdf'
                with self.policy.open_read(str(path)) as source, staged.open('wb') as dest:
                    shutil.copyfileobj(source,dest)
                args = ['/input/0'] if name=='pdf_info' else ['-f','1','-l','30','/input/0','-']
                return self.sandbox.run(name,args,inputs=[staged])
        raise Denied('Capability is not implemented')
