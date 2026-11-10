"""Fixed archive parser, run with Python -I inside Bubblewrap, never imported by the broker."""
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tarfile
import zipfile

MAX_BYTES=2*1024**3
MAX_FILES=10000

def safe_name(value):
    p=PurePosixPath(value)
    if not value or p.is_absolute() or any(x in ('','..','.') for x in value.rstrip('/').split('/')):
        raise ValueError('Unsafe archive path')
    if '\\' in value or ':' in value or '\x00' in value:raise ValueError('Unsafe archive path')
    if any(x in ('.git','.obsidian','.env','__pycache__') or x.startswith('.env.') for x in p.parts):
        raise ValueError('Protected archive entry')
    return p.as_posix()

def members(path):
    if zipfile.is_zipfile(path):
        archive=zipfile.ZipFile(path)
        try:
            for item in archive.infolist():
                mode=(item.external_attr>>16)&0xffff
                if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode))):
                    raise ValueError('Special archive entry')
                if item.flag_bits&1:raise ValueError('Encrypted archives are not supported')
                if item.file_size>max(1024**2,item.compress_size*1000):raise ValueError('Archive expansion limit')
                yield item.filename,item.file_size,item.is_dir(),lambda item=item:archive.open(item)
        finally:archive.close()
    else:
        archive=tarfile.open(path,'r:*')
        try:
            for item in archive:
                if not (item.isfile() or item.isdir()):raise ValueError('Links and special entries are not permitted')
                yield item.name,item.size,item.isdir(),lambda item=item:archive.extractfile(item)
        finally:archive.close()

def inspect_or_extract(path,extract):
    seen=set();total=0;listing=[];output=Path('/output/data')
    if extract:output.mkdir(mode=0o700)
    for name,size,directory,opener in members(path):
        name=safe_name(name)
        if name in seen:raise ValueError('Duplicate archive entry')
        seen.add(name);total+=size
        if len(seen)>MAX_FILES or total>MAX_BYTES:raise ValueError('Archive size limit')
        if len(listing)<100:listing.append({'name':name,'bytes':size,'directory':directory})
        if not extract:continue
        target=output/name
        if directory:target.mkdir(parents=True,exist_ok=True,mode=0o700);continue
        target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        written=0
        with opener() as source,target.open('xb') as dest:
            while chunk:=source.read(1024*1024):
                written+=len(chunk)
                if written>size:raise ValueError('Archive declared size mismatch')
                dest.write(chunk)
            if written!=size:raise ValueError('Archive truncated')
            dest.flush();os.fsync(dest.fileno())
    return {'entries':listing,'count':len(seen),'bytes':total,'truncated':len(seen)>len(listing)}

def main():
    os.umask(0o077)
    config=json.loads(Path('/input/0').read_text())
    if config['operation'] in ('inspect','extract'):
        result=inspect_or_extract('/input/1',config['operation']=='extract')
    elif config['operation']=='create':
        names=config['names']
        if len(names)>MAX_FILES or len(set(names))!=len(names):raise ValueError('Archive entry limit or duplicate')
        with zipfile.ZipFile('/output/archive.zip','x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as archive:
            for index,name in enumerate(names,1):archive.write('/input/'+str(index),safe_name(name))
        result={'count':len(names)}
    else:raise ValueError('Unknown archive operation')
    print(json.dumps(result))

if __name__=='__main__':main()
