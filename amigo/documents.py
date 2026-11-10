"""PDF and archive operations: stage, isolate, verify, then transactional commit."""
import json
from pathlib import Path
import tempfile
from .policy import Denied
from .transactions import Conflict

class Documents:
    def __init__(self,files,sandbox):
        self.files=files;self.policy=files.policy;self.tx=files.transactions;self.sandbox=sandbox

    def pdf(self,sources,destination):
        """Sources contain path + explicit 1-based pages; empty page list selects all."""
        if not 1<=len(sources)<=100:raise Denied('Select between 1 and 100 PDF inputs')
        dest=self.policy.path(destination,exists=False)
        with tempfile.TemporaryDirectory(prefix='o-amigo-pdf-') as directory:
            root=Path(directory);out=root/'out';out.mkdir();inputs=[];selection=[];expected_pages=0
            expected_dest=(self.tx.current(dest) or {}).get('sha256')
            for index,item in enumerate(sources):
                staged=self.files.stage(self.policy.path(item['path']),root/str(index));inputs.append(staged)
                pages=int(self.sandbox.run('pdf_pages',['--show-npages','/input/0'],inputs=[staged],cancel=self.files.cancel).strip())
                wanted=item.get('pages',[])
                if any(type(n)is not int or n<1 or n>pages for n in wanted):raise Denied('Page outside PDF range')
                if len(wanted)>10000:raise Denied('Too many pages')
                expected_pages+=len(wanted) if wanted else pages
                selection.extend([f'/input/{index}',','.join(str(n) for n in wanted) if wanted else '1-z'])
            self.sandbox.run('pdf_pages',['/input/0','--pages',*selection,'--','/output/result.pdf'],inputs=inputs,output=out,cancel=self.files.cancel,timeout=120)
            result=out/'result.pdf'
            self.sandbox.run('pdf_pages',['--check','/input/0'],inputs=[result],cancel=self.files.cancel)
            actual=int(self.sandbox.run('pdf_pages',['--show-npages','/input/0'],inputs=[result],cancel=self.files.cancel))
            if actual!=expected_pages:raise Conflict('PDF page count verification failed')
            operation=self.tx.apply([{'path':dest,'staged':result,'expected':expected_dest}],self.files.cancel)
            return operation|{'pages':actual,'note':'Document-level metadata comes from the first PDF; review outlines and tags after page changes.'}

    def split_pdf(self,path,pages,destination):
        if not pages or len(pages)>1000:raise Denied('Select 1 to 1000 pages')
        dest=self.policy.path(destination,exists=False)
        if dest.exists():raise Conflict('Split destination must be a new folder')
        with tempfile.TemporaryDirectory(prefix='o-amigo-split-') as directory:
            root=Path(directory);data=root/'data';data.mkdir();staged=self.files.stage(self.policy.path(path),root/'input')
            count=int(self.sandbox.run('pdf_pages',['--show-npages','/input/0'],inputs=[staged],cancel=self.files.cancel))
            if len(set(pages))!=len(pages) or any(type(p)is not int or not 1<=p<=count for p in pages):raise Denied('Invalid or duplicate page')
            for page in pages:
                self.sandbox.run('pdf_pages',['/input/0','--pages','/input/0',str(page),'--',f'/output/page-{page:04d}.pdf'],inputs=[staged],output=data,cancel=self.files.cancel)
                output=data/f'page-{page:04d}.pdf'
                self.sandbox.run('pdf_pages',['--check','/input/0'],inputs=[output],cancel=self.files.cancel)
            return self.tx.install_tree(data,dest,self.files.cancel)|{'pages':len(pages)}

    def archive(self,operation,path=None,destination=None,sources=None):
        with tempfile.TemporaryDirectory(prefix='o-amigo-archive-') as directory:
            root=Path(directory);out=root/'out';out.mkdir();inputs=[];config={'operation':operation}
            if operation=='create':
                names=[]
                for source in sources or []:
                    src=self.policy.path(source)
                    candidates=[src]
                    if src.is_dir():
                        found=self.files.search(str(src),limit=500)
                        if found['truncated']:raise Denied('Archive folder exceeds 500 entries; select smaller folders')
                        candidates=[Path(p) for p in found['matches']]
                    for candidate in candidates:
                        if candidate.is_dir():continue
                        names.append((Path(src.name)/candidate.relative_to(src)).as_posix() if src.is_dir() else src.name)
                        inputs.append(self.files.stage(candidate,root/f'file-{len(inputs)}'))
                if not inputs:raise Denied('No files selected')
                config['names']=names
            else:inputs=[self.files.stage(self.policy.path(path),root/'archive')]
            config_path=root/'request.json';config_path.write_text(json.dumps(config))
            result=json.loads(self.sandbox.run('archive',[],inputs=[config_path,*inputs],output=out,timeout=120,cancel=self.files.cancel))
            if operation=='extract':return result|self.tx.install_tree(out/'data',destination,self.files.cancel)
            if operation=='create':
                dest=self.policy.path(destination,exists=False)
                if dest.exists():raise Conflict('Archive destination already exists')
                return result|self.tx.apply([{'path':dest,'staged':out/'archive.zip','expected':None}],self.files.cancel)
            return result
