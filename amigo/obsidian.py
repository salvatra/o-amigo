"""Conservative vault adapter: resolve links, stage all edits, verify, commit together.

No Obsidian plugins, scripts or app automation are executed. Ambiguous links,
unsupported canvas data and conflicting concurrent edits abort before mutation.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import tempfile
from urllib.parse import quote, unquote, urlsplit
from .policy import Denied
from .transactions import Conflict

@dataclass
class Link:
    start:int
    end:int
    target:str
    wiki:bool=False

def links(text):
    """Locate native wiki, inline Markdown and reference-definition destinations.
    Fenced code, inline code and HTML comments are intentionally left untouched.
    """
    ignored=[];fence=None;offset=0
    for line in text.splitlines(keepends=True):
        match=re.match(r'^ {0,3}(`{3,}|~{3,})',line)
        if fence:
            if match and match[1][0]==fence[0] and len(match[1])>=len(fence):
                ignored.append((begin,offset+len(line)));fence=None
        elif match:fence=match[1];begin=offset
        offset+=len(line)
    if fence:ignored.append((begin,len(text)))
    ignored.extend((m.start(),m.end()) for m in re.finditer(r'<!--.*?-->|(`+)(?!`)(.*?)\1(?!`)',text,re.S))
    def hidden(start):return any(a<=start<b for a,b in ignored)
    found=[]
    for match in re.finditer(r'(?<!\\)\[\[([^\]\n]+)\]\]',text):
        if hidden(match.start()):continue
        target=match[1].split('|',1)[0];start=match.start(1)
        found.append(Link(start,start+len(target),target,True))
    for match in re.finditer(r'(?<!\\)\]\(',text):
        if hidden(match.start()):continue
        start=match.end()
        while start<len(text) and text[start] in ' \t':start+=1
        if start>=len(text):continue
        if text[start]=='<':
            start+=1;end=text.find('>',start)
            if end<0:continue
        else:
            end=start;depth=0
            while end<len(text):
                char=text[end]
                if char=='\\':end+=2;continue
                if char=='(':depth+=1
                if char==')':
                    if depth==0:break
                    depth-=1
                if char.isspace() and depth==0:break
                end+=1
            if end>=len(text) or depth:continue
        if end>start:found.append(Link(start,end,text[start:end]))
    for match in re.finditer(r'^ {0,3}\[[^\]\n]+\]:[ \t]*(?:<([^>\n]+)>|([^\s]+))',text,re.M):
        if hidden(match.start()):continue
        group=1 if match[1] is not None else 2
        found.append(Link(match.start(group),match.end(group),match[group]))
    for match in re.finditer(r'<[^>]*?\b(?:src|href)\s*=\s*([\"\'])(.*?)\1[^>]*>',text,re.S|re.I):
        if not hidden(match.start()):found.append(Link(match.start(2),match.end(2),match[2]))
    unique={ (item.start,item.end):item for item in found }
    return sorted(unique.values(),key=lambda item:item.start)

def target_parts(target):
    path,sep,fragment=target.partition('#')
    return unquote(re.sub(r'\\([ ()])',r'\1',path)),sep+fragment

def resolve(target,note,files,wiki=False):
    raw,_=target_parts(target)
    if not raw:return note if target.startswith('#') else None
    if urlsplit(raw).scheme or raw.startswith('//'):return None
    options=[raw.lstrip('/'),posixpath.normpath(posixpath.join(posixpath.dirname(note),raw))]
    if not wiki:options.reverse()
    def variants(value):return [value,value+'.md'] if not PurePosixPath(value).suffix else [value]
    for option in options:
        for candidate in variants(option):
            if candidate in files:return candidate
    # Obsidian's shortest-path links are only safe to resolve when unique.
    possibilities={file for file in files if any(file==v or file.endswith('/'+v) for v in variants(raw.lstrip('/')))}
    if len(possibilities)>1:raise Conflict('Ambiguous vault link: '+target)
    return next(iter(possibilities),None)

class Obsidian:
    def __init__(self,files):self.files=files;self.policy=files.policy;self.tx=files.transactions

    def inventory(self,vault):
        root=self.policy.path(vault)
        if not (root/'.obsidian').is_dir():raise Denied('Select the root of an Obsidian vault')
        result=[]
        for directory,dirs,names in os.walk(root,followlinks=False):
            self.files.check_cancel();allowed=[]
            for name in dirs:
                try:self.policy.path(str(Path(directory)/name));allowed.append(name)
                except (Denied,OSError):pass
            dirs[:]=allowed
            for name in names:
                path=Path(directory)/name
                try:self.policy.path(str(path))
                except (Denied,OSError):continue
                result.append(path.relative_to(root).as_posix())
                if len(result)>20000:raise Denied('Vault exceeds 20,000 files; select operations manually')
        return root,set(result)

    def move(self,vault,source,destination):
        root,names=self.inventory(vault)
        src=self.policy.path(source);dest=self.policy.path(destination,exists=False)
        if not src.is_relative_to(root) or not dest.is_relative_to(root):raise Denied('Both paths must be inside the vault')
        if not src.is_file() or dest.exists():raise Conflict('Move requires a file and an unused destination')
        if src.suffix!=dest.suffix:raise Denied('Moving a vault file cannot change its format')
        old=src.relative_to(root).as_posix();new=dest.relative_to(root).as_posix()
        after=(names-{old})|{new};changes=[];updated=[];total=0
        with tempfile.TemporaryDirectory(prefix='o-amigo-vault-') as directory:
            stage=Path(directory)
            source_copy=self.files.stage(src,stage/'source')
            with source_copy.open('rb') as file:source_hash=hashlib.file_digest(file,'sha256').hexdigest()
            moved_staged=source_copy
            for name in sorted(names):
                self.files.check_cancel()
                if not name.endswith(('.md','.canvas')):continue
                with self.policy.open_read(str(root/name)) as file:original=file.read(16*1024**2+1)
                total+=len(original)
                if len(original)>16*1024**2 or total>128*1024**2:raise Denied('Vault text exceeds safe batch size')
                text=original.decode('utf-8');new_name=new if name==old else name
                if name.endswith('.canvas'):
                    data=json.loads(text);changed=False
                    if not isinstance(data,dict) or not isinstance(data.get('nodes',[]),list):raise Denied('Unsupported canvas format')
                    for node in data.get('nodes',[]):
                        if node.get('type')=='file' and node.get('file')==old:node['file']=new;changed=True
                        if node.get('type')=='text':
                            rewritten=self.rewrite(node.get('text',''),name,new_name,names,after,old,new)
                            if rewritten!=node.get('text',''):node['text']=rewritten;changed=True
                    rewritten=json.dumps(data,ensure_ascii=False,indent=2) if changed else text
                else:rewritten=self.rewrite(text,name,new_name,names,after,old,new)
                if rewritten==text:continue
                prepared=stage/f'note-{len(changes)}';prepared.write_text(rewritten)
                updated.append(new_name)
                if name==old:moved_staged=prepared
                else:changes.append({'path':root/name,'staged':prepared,'expected':hashlib.sha256(original).hexdigest()})
            changes.extend([{'path':dest,'staged':moved_staged,'expected':None},{'path':src,'staged':None,'expected':source_hash}])
            result=self.tx.apply(changes,self.files.cancel)
            return result|{'moved':new,'updated_notes':updated,'verified':'Resolved native note and canvas links before committing'}

    @staticmethod
    def rewrite(text,name,new_name,before,after,old,new):
        replacements=[]
        for link in links(text):
            target=resolve(link.target,name,before,link.wiki)
            if target is None:continue
            expected=new if target==old else target
            try:unchanged=resolve(link.target,new_name,after,link.wiki)==expected
            except Conflict:unchanged=False
            if unchanged:continue
            raw,fragment=target_parts(link.target)
            if link.wiki:
                path=expected
                if not PurePosixPath(raw).suffix and path.endswith('.md'):path=path[:-3]
            else:path=quote(posixpath.relpath(expected,posixpath.dirname(new_name) or '.'),safe='/._-~')
            replacement=path+fragment
            if resolve(replacement,new_name,after,link.wiki)!=expected:raise Conflict('Cannot preserve a vault link')
            replacements.append((link.start,link.end,replacement))
        for start,end,value in reversed(replacements):text=text[:start]+value+text[end:]
        return text
