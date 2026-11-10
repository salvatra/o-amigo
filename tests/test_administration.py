import copy
import unittest
from amigo.approval import ApprovalGate,ApprovalRequired
from amigo.policy import Denied
from amigo.packages import Packages,names
from amigo.devices import Devices,BLOCK,DRIVE,FS

class PackageBackend:
    def __init__(self):self.installed=False;self.executions=0;self.removal=False;self.version='1.0'
    def repositories(self):return ['extra']
    def package(self):return {'id':f'example;{self.version};x86_64;'+('installed' if self.installed else 'extra'),'name':'example','version':self.version,'architecture':'x86_64','repository':'installed' if self.installed else 'extra','action':'installed' if self.installed else 'available','summary':'Example'}
    def resolve(self,requested):return [self.package()] if requested==['example'] else []
    def simulate(self,ids):return [self.package()|{'action':'removing' if self.removal else 'installing'}]
    def install(self,ids):self.executions+=1;self.installed=True

class AdministrationTests(unittest.TestCase):
    def test_package_names_are_not_commands_or_local_paths(self):
        for value in [['--root'],['/tmp/file.pkg.tar.zst'],['x;touch'],['x/y'],['x\n'],[],['-Syu']]:
            with self.assertRaises(Denied):names(value)
    def test_package_prepare_approve_execute_verify(self):
        backend=PackageBackend();gate=ApprovalGate();packages=Packages(gate,backend=backend)
        with self.assertRaises(ApprovalRequired) as pending:packages.install(['example'])
        self.assertEqual(backend.executions,0);gate.decide(pending.exception.token,True)
        self.assertTrue(packages.install(['example'])['verified']);self.assertEqual(backend.executions,1)
        self.assertEqual(packages.install(['example']),{'already_installed':['example']})
    def test_repository_removal_and_changed_version_fail_closed(self):
        backend=PackageBackend();gate=ApprovalGate();packages=Packages(gate,backend=backend)
        backend.removal=True
        with self.assertRaises(Denied):packages.install(['example'])
        backend.removal=False
        with self.assertRaises(ApprovalRequired) as pending:packages.install(['example'])
        gate.decide(pending.exception.token,True);backend.version='2.0'
        with self.assertRaises(ApprovalRequired):packages.install(['example'])
        self.assertEqual(backend.executions,0)
        with self.assertRaises(Denied):packages.install(['not-in-repository'])
    def test_restart_does_not_preserve_grants(self):
        gate=ApprovalGate()
        with self.assertRaises(ApprovalRequired) as pending:gate.require({'target':'one'})
        new=ApprovalGate()
        with self.assertRaises(Denied):new.decide(pending.exception.token,True)

class DeviceBackend:
    def __init__(self):
        self.calls=[];self.data={'/drive':{DRIVE:{'Id':'device','ConnectionBus':'usb','Model':'Fixture','CanPowerOff':True}},
          '/volume':{BLOCK:{'Drive':'/drive','HintSystem':False,'IdUsage':'filesystem','IdUUID':'uuid','Size':1024,'IdType':'exfat'},FS:{'MountPoints':[]}},
          '/internal':{BLOCK:{'Drive':'/drive','HintSystem':True,'IdUsage':'filesystem','IdUUID':'root'},FS:{'MountPoints':[]}}}
    def objects(self):return copy.deepcopy(self.data)
    def action(self,path,interface,method):
        self.calls.append((path,interface,method))
        if method=='Mount':self.data[path][FS]['MountPoints']=[b'/run/media/test/fixture\0']
        if method=='Unmount':self.data[path][FS]['MountPoints']=[]
    def close(self):pass

class DeviceTests(unittest.TestCase):
    def test_requires_selection_and_excludes_system_filesystems(self):
        backend=DeviceBackend();devices=Devices(backend=backend);rows=devices.identify()
        self.assertEqual(len(rows),1);self.assertFalse(rows[0]['selected'])
        with self.assertRaises(Denied):devices.mount(rows[0]['id'])
        self.assertEqual(backend.calls,[])
    def test_mount_unmount_eject_and_no_force(self):
        backend=DeviceBackend();identifier=Devices(backend=backend).identify()[0]['id'];devices=Devices([identifier],backend=backend)
        self.assertTrue(devices.mount(identifier)['verified'])
        with self.assertRaises(Denied):devices.eject(identifier)
        self.assertTrue(devices.unmount(identifier)['verified']);self.assertTrue(devices.eject(identifier)['verified'])
        self.assertEqual([c[2] for c in backend.calls],['Mount','Unmount','PowerOff'])
    def test_replaced_media_and_unsafe_mount_do_not_inherit_permission(self):
        backend=DeviceBackend();identifier=Devices(backend=backend).identify()[0]['id'];devices=Devices([identifier],backend=backend)
        backend.data['/volume'][FS]['MountPoints']=[b'/home\0']
        self.assertEqual(devices.authorized_mounts(),[])
        backend.data['/volume'][BLOCK]['IdUUID']='changed'
        with self.assertRaises(Denied):devices.unmount(identifier)

if __name__=='__main__':unittest.main()

from amigo.printers import Printers,device_uri,printer_name

class PrinterBackend:
    def __init__(self):self.printer={'device-uri':'ipp://printer.local/ipp/print','printer-state':3};self.calls=[];self.job_rows=[]
    def printers(self):return {'Fixture':dict(self.printer)} if self.printer else {}
    def jobs(self):return self.job_rows
    def default(self):return 'Fixture'
    def drivers(self):return {'installed-driver':{}}
    def admin(self,method,*args):
        self.calls.append((method,args))
        if method=='PrinterAdd':self.printer={'device-uri':args[1],'printer-state':3}
        if method=='PrinterSetEnabled':self.printer['printer-state']=3 if args[1] else 5
        if method=='JobCancelPurge':self.job_rows=[]

class PrinterTests(unittest.TestCase):
    def test_device_uri_never_accepts_file_credentials_or_shell(self):
        for uri in ['file:///etc/passwd','ipp://user:password@printer/print','http://printer/','socket://printer:22','ipp://printer/a\nB']:
            with self.assertRaises((Denied,ValueError)):device_uri(uri)
        for name in ['--help','../printer','x; command']:
            with self.assertRaises(Denied):printer_name(name)
    def test_configuration_requires_plan_approval_and_valid_driver(self):
        api=PrinterBackend();gate=ApprovalGate();p=Printers(gate,backend=api)
        with self.assertRaises(Denied):p.configure('Fixture','usb://Printer/model','everywhere')
        with self.assertRaises(Denied):p.configure('Fixture','ipp://printer.local/ipp/print','/tmp/evil.ppd')
        with self.assertRaises(ApprovalRequired) as pending:p.configure('Fixture','ipp://printer.local/ipp/print')
        self.assertEqual(api.calls,[]);gate.decide(pending.exception.token,True)
        self.assertTrue(p.configure('Fixture','ipp://printer.local/ipp/print')['verified'])
        self.assertEqual(api.calls[0][0],'PrinterAdd')
    def test_queue_actions_are_bound_to_printer_job_and_state(self):
        api=PrinterBackend();gate=ApprovalGate();p=Printers(gate,backend=api)
        api.job_rows=[{'id':12,'job-printer-uri':'ipp://localhost/printers/Other','job-state':3}]
        with self.assertRaises(Denied):p.action('Fixture','cancel_job',12)
        api.job_rows[0]['job-printer-uri']='ipp://localhost/printers/Fixture'
        with self.assertRaises(ApprovalRequired) as pending:p.action('Fixture','cancel_job',12)
        gate.decide(pending.exception.token,True);self.assertTrue(p.action('Fixture','cancel_job',12)['verified'])
        self.assertEqual(api.calls,[('JobCancelPurge',(12,False))])
    def test_printer_change_invalidates_approval(self):
        api=PrinterBackend();gate=ApprovalGate();p=Printers(gate,backend=api)
        with self.assertRaises(ApprovalRequired) as pending:p.action('Fixture','pause')
        gate.decide(pending.exception.token,True);api.printer['device-uri']='ipp://other.local/ipp/print'
        with self.assertRaises(ApprovalRequired):p.action('Fixture','pause')
        self.assertEqual(api.calls,[])
