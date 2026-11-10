import io
import json
import os
from pathlib import Path
import stat
import tarfile
import tempfile
import threading
import unittest
import zipfile
from amigo.policy import Policy,Denied
from amigo.transactions import Transactions,Conflict,Cancelled
from amigo.tools import Tools

def sample_pdf(path):
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>']
    for word,content in [('First',4),('Second',6)]:
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 7 0 R >> >> /Contents {content} 0 R >>'.encode())
        stream=f'BT /F1 24 Tf 20 150 Td ({word}) Tj ET'.encode()
        objects.append(f'<< /Length {len(stream)} >>\nstream\n'.encode()+stream+b'\nendstream')
    objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    data=bytearray(b'%PDF-1.4\n');offsets=[0]
    for index,obj in enumerate(objects,1):
        offsets.append(len(data));data+=f'{index} 0 obj\n'.encode()+obj+b'\nendobj\n'
    xref=len(data);data+=f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    for offset in offsets[1:]:data+=f'{offset:010d} 00000 n \n'.encode()
    data+=f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode();path.write_bytes(data)

class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.data=self.root/'data';self.data.mkdir()
        self.policy=Policy([self.data]);self.tx=Transactions(self.root/'recovery',self.policy);self.tools=Tools(self.policy,self.tx)
    def tearDown(self):self.tx.close();self.tmp.cleanup()
    def test_pdf_reorder_merge_split_and_undo(self):
        pdf=self.data/'original.pdf';sample_pdf(pdf);output=self.data/'reordered.pdf'
        result=self.tools.call('pdf_pages',{'sources':[{'path':str(pdf),'pages':[2,1,2]}],'destination':str(output)})
        self.assertEqual(result['pages'],3)
        text=self.tools.call('pdf_text',{'path':str(output)})
        self.assertLess(text.index('Second'),text.index('First'));self.assertEqual(text.count('Second'),2)
        split=self.tools.call('pdf_split',{'path':str(pdf),'pages':[1,2],'destination':str(self.data/'split')})
        self.assertEqual(len(list((self.data/'split').glob('*.pdf'))),2)
        self.tx.undo(split['operation_id']);self.assertFalse((self.data/'split').exists())
        self.tx.undo(result['operation_id']);self.assertFalse(output.exists());self.assertTrue(pdf.exists())
    def test_pdf_bad_page_no_output(self):
        pdf=self.data/'original.pdf';sample_pdf(pdf)
        with self.assertRaises(Denied):self.tools.call('pdf_pages',{'sources':[{'path':str(pdf),'pages':[3]}],'destination':str(self.data/'bad.pdf')})
        self.assertFalse((self.data/'bad.pdf').exists())
    def test_archive_roundtrip_unicode(self):
        source=self.data/'ação.txt';source.write_text('Olá, São João!')
        archive=self.data/'files.zip'
        self.tools.call('archive_create',{'sources':[str(source)],'destination':str(archive)})
        info=self.tools.call('archive_info',{'path':str(archive)});self.assertEqual(info['count'],1)
        result=self.tools.call('archive_extract',{'path':str(archive),'destination':str(self.data/'unpacked')})
        self.assertEqual((self.data/'unpacked'/'ação.txt').read_text(),source.read_text())
        self.tx.undo(result['operation_id']);self.assertFalse((self.data/'unpacked').exists())
    def test_archive_nested_and_conflicting_undo(self):
        archive=self.data/'files.zip'
        with zipfile.ZipFile(archive,'w') as z:z.writestr('a/b/file.txt','original')
        result=self.tools.call('archive_extract',{'path':str(archive),'destination':str(self.data/'unpacked')})
        (self.data/'unpacked/a/b/file.txt').write_text('user modified')
        with self.assertRaises(Conflict):self.tx.undo(result['operation_id'])
        self.assertEqual((self.data/'unpacked/a/b/file.txt').read_text(),'user modified')
    def test_archive_traversal_symlink_and_protected(self):
        for name in ['../escape','/tmp/escape','dir/../../escape','C:\\escape','.env','a/.git/config']:
            archive=self.data/'bad.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr(name,'bad')
            with self.assertRaises(RuntimeError):self.tools.call('archive_extract',{'path':str(archive),'destination':str(self.data/'output')})
            self.assertFalse((self.data/'output').exists())
        with zipfile.ZipFile(archive,'w') as z:
            entry=zipfile.ZipInfo('link');entry.create_system=3;entry.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(entry,'/etc/passwd')
        with self.assertRaises(RuntimeError):self.tools.call('archive_extract',{'path':str(archive),'destination':str(self.data/'output')})
    def test_tar_link_rejected(self):
        archive=self.data/'bad.tar'
        with tarfile.open(archive,'w') as t:
            item=tarfile.TarInfo('link');item.type=tarfile.LNKTYPE;item.linkname='/etc/passwd';t.addfile(item)
        with self.assertRaises(RuntimeError):self.tools.call('archive_extract',{'path':str(archive),'destination':str(self.data/'output')})
    def test_schema_nested_injection(self):
        with self.assertRaises(Denied):self.tools.call('pdf_pages',{'sources':[{'path':'--help','pages':['1;sh']}],'destination':str(self.data/'bad')})
        with self.assertRaises(Denied):self.tools.call('archive_create',{'sources':['/etc/passwd'],'destination':str(self.data/'bad')})
        with self.assertRaises(Denied):self.tools.call('set_file_times',{'path':'x','mtime':'2024-01-01','ctime':'y','timezone':'UTC'})
    def test_sandbox_cancel(self):
        event=threading.Event();event.set();self.tools.cancel=event
        with self.assertRaises(Cancelled):self.tools.call('read_manual',{'name':'ls'})
    def test_vault_generic_move_refused(self):
        (self.data/'.obsidian').mkdir();p=self.data/'note.md';p.write_text('note')
        with self.assertRaises(Denied):self.tools.call('move_file',{'source':str(p),'destination':str(self.data/'new.md')})
        self.assertTrue(p.exists())

if __name__=='__main__':unittest.main()
