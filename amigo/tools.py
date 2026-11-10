"""Closed, strictly validated capability registry. No shell or policy mutation tool."""
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from .policy import Denied
from .sandbox import Sandbox
from .schema import validate
from .files import Files
from .documents import Documents
from .obsidian import Obsidian

TEXT={'type':'string'}
PAGES={'type':'array','items':{'type':'integer','minimum':1,'maximum':1000000},'maxItems':10000}

SPECS = [
 ('list_files', 'List an authorized folder. Protected entries are omitted.', {'path':{'type':'string'}}, ['path']),
 ('read_file', 'Read a bounded UTF-8 text file in an authorized folder.', {'path':{'type':'string'}}, ['path']),
 ('file_info', 'Inspect file size and timestamps without changing them.', {'path':{'type':'string'}}, ['path']),
 ('hash_file', 'Calculate the SHA-256 of an authorized file.', {'path':{'type':'string'}}, ['path']),
 ('read_manual', 'Read an installed system manual. No commands are executed from the manual.',
  {'name':{'type':'string'},'section':{'type':'string'}}, ['name']),
 ('pdf_info', 'Inspect PDF metadata and page count.', {'path':{'type':'string'}}, ['path']),
 ('pdf_text', 'Extract PDF text (bounded output).', {'path':{'type':'string'}}, ['path']),
 ('search_files','Search authorized file names and optional text; no background indexing.',
  {'path':TEXT,'pattern':TEXT,'text':TEXT,'limit':{'type':'integer','minimum':1,'maximum':500}},['path']),
 ('create_folder','Create a new empty folder with recovery.',{'path':TEXT},['path']),
 ('write_file','Create or replace UTF-8 text with a verified recovery copy.',{'path':TEXT,'text':{'type':'string','maxLength':131072}},['path','text']),
 ('edit_file','Replace exactly one matching occurrence; refuse ambiguous edits.',{'path':TEXT,'old':{'type':'string','maxLength':65536},'new':{'type':'string','maxLength':65536}},['path','old','new']),
 ('copy_file','Copy a file to a new path; verify SHA-256. Never overwrite.',{'source':TEXT,'destination':TEXT},['source','destination']),
 ('move_file','Move or rename a file to a new path with recovery. Use obsidian_move for vaults.',{'source':TEXT,'destination':TEXT},['source','destination']),
 ('trash_file','Send a file to the desktop Trash, keeping a recovery copy.',{'path':TEXT},['path']),
 ('set_file_times','Change mtime and optional atime. ISO 8601 dates; timezone applies to dates without offset. Cannot change ctime or birth date.',
  {'path':TEXT,'mtime':TEXT,'atime':TEXT,'timezone':TEXT},['path','mtime','timezone']),
 ('pdf_pages','Select, reorder, remove or merge pages into a PDF. Each source has 1-based page numbers; [] means all pages. Metadata comes from first PDF.',
  {'sources':{'type':'array','minItems':1,'maxItems':100,'items':{'type':'object','properties':{'path':TEXT,'pages':PAGES},'required':['path'],'additionalProperties':False}},'destination':TEXT},['sources','destination']),
 ('pdf_split','Split selected pages into separate PDFs in a new folder.',{'path':TEXT,'pages':PAGES,'destination':TEXT},['path','pages','destination']),
 ('archive_info','Inspect ZIP or TAR metadata in isolation.',{'path':TEXT},['path']),
 ('archive_extract','Safely extract ZIP or TAR into a new folder; rejects links, traversal and bombs.',{'path':TEXT,'destination':TEXT},['path','destination']),
 ('archive_create','Create ZIP from authorized files or folders, excluding protected paths.',{'sources':{'type':'array','items':TEXT,'minItems':1,'maxItems':100},'destination':TEXT},['sources','destination']),
 ('obsidian_search','Search Markdown notes in an explicitly selected Obsidian vault.',{'vault':TEXT,'text':TEXT,'limit':{'type':'integer','minimum':1,'maximum':500}},['vault','text']),
 ('obsidian_move','Move or rename a note/attachment within a vault, updating native wiki, Markdown and canvas links in one recoverable batch. Refuses ambiguous links.',{'vault':TEXT,'source':TEXT,'destination':TEXT},['vault','source','destination']),
]

def schemas():
    return [{'type':'function','function':{'name':name,'description':description,
             'parameters':{'type':'object','properties':props,'required':required,'additionalProperties':False}}}
            for name,description,props,required in SPECS]

class Tools:
    def __init__(self, policy, transactions=None, cancel=None):
        self.policy = policy
        self.sandbox = Sandbox()
        self.files = Files(policy,transactions,cancel) if transactions else None
        self.documents = Documents(self.files,self.sandbox) if self.files else None
        self.cancel=cancel

    def call(self, name, args):
        spec = next((s for s in SPECS if s[0] == name), None)
        if not spec or not isinstance(args, dict):
            raise Denied('Unknown tool')
        validate(args,{'type':'object','properties':spec[2],'required':spec[3]})
        writes={'create_folder','write_file','edit_file','copy_file','move_file','trash_file','set_file_times',
                'pdf_pages','pdf_split','archive_create','archive_extract','obsidian_move'}
        if name in writes and not self.files:raise Denied('Writes are not authorized')
        if name=='search_files':
            return Files(self.policy,None,self.cancel).search(args['path'],args.get('pattern','*'),args.get('text'),args.get('limit',100))
        if name=='create_folder':return self.files.mkdir(args['path'])
        if name=='write_file':return self.files.write(**args)
        if name=='edit_file':return self.files.replace(**args)
        if name in ('copy_file','move_file'):return self.files.copy(**args,move=name=='move_file')
        if name=='trash_file':return self.files.trash(args['path'])
        if name=='set_file_times':return self.files.timestamps(**args)
        if name=='pdf_pages':return self.documents.pdf(**args)
        if name=='pdf_split':return self.documents.split_pdf(**args)
        if name=='obsidian_move':return Obsidian(self.files).move(**args)
        if name=='obsidian_search':
            files=self.files or Files(self.policy,None,self.cancel)
            vault,_=Obsidian(files).inventory(args['vault'])
            return files.search(str(vault),'*.md',args['text'],args.get('limit',100))
        if name.startswith('archive_'):
            documents=self.documents or Documents(Files(self.policy,None,self.cancel),self.sandbox)
            return documents.archive({'archive_info':'inspect','archive_extract':'extract','archive_create':'create'}[name],**args)
        if name == 'read_manual':
            topic = args['name']; section = args.get('section','')
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+-]{0,79}', topic):
                raise Denied('Invalid manual name')
            if section and not re.fullmatch(r'[1-9][A-Za-z0-9]{0,5}', section):
                raise Denied('Invalid manual section')
            return self.sandbox.run('man', ['-P','cat',*( [section] if section else []),topic],cancel=self.cancel)
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
                return self.sandbox.run(name,args,inputs=[staged],cancel=self.cancel)
        raise Denied('Capability is not implemented')
