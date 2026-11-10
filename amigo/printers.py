"""Bounded CUPS reads and concrete approved actions through CupsPkHelper.

No server configuration, PPD uploads, file:// devices or arbitrary CUPS options.
"""
import hashlib
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
from .policy import Denied
from .transactions import Cancelled

NAME=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,126}\Z')

def printer_name(value):
    if not isinstance(value,str) or not NAME.fullmatch(value):raise Denied('Nome de impressora inválido.')
    return value

def device_uri(value):
    if not isinstance(value,str) or len(value)>2048 or any(ord(c)<33 for c in value) or '\\' in value:raise Denied('URI de impressora inválido.')
    uri=urlsplit(value)
    if uri.scheme not in ('ipp','ipps','usb','dnssd','socket','lpd') or not uri.hostname or uri.username or uri.password or uri.fragment:
        raise Denied('Só são permitidas impressoras IPP/IPPS, USB, DNS-SD, JetDirect ou LPD, sem credenciais no URI.')
    if uri.scheme in ('ipp','ipps','socket','lpd') and uri.port and uri.port not in (631,443,9100,515):raise Denied('Porta de impressão não permitida.')
    return value

class Cups:
    def __init__(self):
        try:import cups
        except ImportError as error:raise RuntimeError('Instala python-pycups para usar impressoras.') from error
        # Never inherit a user-selected remote CUPS server or an interactive password callback.
        cups.setPasswordCB2(lambda *args:'');self.cups=cups;self.connection=cups.Connection(host='/run/cups/cups.sock')
    def printers(self):
        fields=('device-uri','printer-info','printer-location','printer-state','printer-state-message','printer-is-accepting-jobs','printer-is-shared','printer-make-and-model')
        return {name:{k:v for k,v in info.items() if k in fields} for name,info in self.connection.getPrinters().items()}
    def jobs(self):
        fields=('job-printer-uri','job-name','job-originating-user-name','job-state','job-state-reasons','job-k-octets','job-impressions-completed')
        return [{'id':int(identifier),**{k:v for k,v in job.items() if k in fields}} for identifier,job in self.connection.getJobs(which_jobs='not-completed',limit=100).items()]
    def devices(self):return self.connection.getDevices(limit=100,include_schemes=['ipp','ipps','usb','dnssd','socket','lpd'])
    def drivers(self):return self.connection.getPPDs()
    def default(self):return self.connection.getDefault()
    def admin(self,method,*args):
        allowed={'PrinterAdd','PrinterDelete','PrinterSetDefault','PrinterSetEnabled','JobCancelPurge','JobSetHoldUntil','JobRestart'}
        if method not in allowed:raise Denied('Operação administrativa CUPS não permitida.')
        import dbus
        bus=dbus.SystemBus(private=True)
        try:
            proxy=dbus.Interface(bus.get_object('org.opensuse.CupsPkHelper.Mechanism','/'),'org.opensuse.CupsPkHelper.Mechanism')
            error=str(getattr(proxy,method)(*args,timeout=120))
            if error:raise RuntimeError('CUPS: '+error[:1000])
        finally:bus.close()
    def print_file(self,name,path,copies):return self.connection.printFile(name,str(path),Path(path).name,{'copies':str(copies)})
    def job(self,identifier):return self.connection.getJobAttributes(identifier,requested_attributes=['job-state','job-printer-uri'])

class Printers:
    def __init__(self,gate,files=None,cancel=None,backend=None):self.gate=gate;self.files=files;self.cancel=cancel;self.backend=backend
    def api(self):
        if self.backend is None:self.backend=Cups()
        return self.backend
    def check_cancel(self):
        if self.cancel and self.cancel.is_set():raise Cancelled('Operação cancelada antes de alterar a impressora.')
    def status(self):return {'printers':self.api().printers(),'jobs':self.api().jobs(),'default':self.api().default()}
    def discover(self):
        result=[]
        for uri,attrs in self.api().devices().items():
            try:device_uri(uri)
            except (Denied,ValueError):continue
            result.append({'uri':uri,'description':str(attrs.get('device-info',''))[:300],'model':str(attrs.get('device-make-and-model',''))[:300]})
        return result[:100]
    def drivers(self,text=''):
        return [{'id':name,'description':str(attrs.get('ppd-make-and-model',''))} for name,attrs in self.api().drivers().items()
                if text.casefold() in (name+' '+str(attrs.get('ppd-make-and-model',''))).casefold()][:100]
    def configure(self,name,uri,driver='everywhere',description='',location=''):
        printer_name(name);device_uri(uri);api=self.api()
        if driver!='everywhere' and driver not in api.drivers():raise Denied('Escolhe um controlador instalado apresentado por printer_drivers.')
        if driver=='everywhere' and urlsplit(uri).scheme not in ('ipp','ipps'):raise Denied('IPP Everywhere exige um URI ipp ou ipps; escolhe um controlador instalado para outros protocolos.')
        for value in (description,location):
            if not isinstance(value,str) or len(value)>256 or any(ord(c)<32 for c in value):raise Denied('Descrição ou localização inválida.')
        before=api.printers().get(name)
        self.gate.require({'operation':'Configurar impressora','printer':name,'before':before,
                           'device_uri':uri,'driver':driver,'description':description,'location':location,
                           'authentication':'CUPS/Polkit; sem partilha na rede nem alterações globais do servidor.'})
        self.check_cancel();api.admin('PrinterAdd',name,uri,driver,description,location)
        after=api.printers().get(name)
        if not after or after.get('device-uri')!=uri:raise RuntimeError('A configuração não foi confirmada. Verifica as definições de impressoras.')
        return {'verified':True,'printer':name,'configuration':after}
    def action(self,name,action,job_id=None):
        printer_name(name);api=self.api();before=api.printers().get(name)
        if before is None:raise Denied('Impressora não encontrada.')
        methods={'pause':('PrinterSetEnabled',(name,False)),'resume':('PrinterSetEnabled',(name,True)),
                 'set_default':('PrinterSetDefault',(name,)),'delete':('PrinterDelete',(name,))}
        jobs={'cancel_job':('JobCancelPurge',(job_id,False)), 'hold_job':('JobSetHoldUntil',(job_id,'indefinite')),
              'release_job':('JobSetHoldUntil',(job_id,'no-hold'))}
        job=None
        if action in jobs:
            if type(job_id)is not int or job_id<=0:raise Denied('Indica um trabalho de impressão válido.')
            job=next((j for j in api.jobs() if j['id']==job_id),None)
            if not job or urlsplit(job.get('job-printer-uri','')).path!='/printers/'+name:raise Denied('O trabalho não pertence à impressora indicada ou já terminou.')
            method,args=jobs[action]
        elif action in methods:
            if job_id is not None:raise Denied('Esta ação não recebe um trabalho.')
            method,args=methods[action]
        else:raise Denied('Ação de impressora não permitida.')
        self.gate.require({'operation':'Alterar impressora ou fila','printer':name,'action':action,'before':before,'job':job})
        self.check_cancel();api.admin(method,*args)
        # Verify the concrete postcondition; don't report printing complete from job submission.
        printers=api.printers()
        if action=='delete':verified=name not in printers
        elif action=='set_default':verified=api.default()==name
        elif action=='pause':verified=printers.get(name,{}).get('printer-state')==5
        elif action=='resume':verified=printers.get(name,{}).get('printer-state') in (3,4)
        else:
            current=next((j for j in api.jobs() if j['id']==job_id),None)
            verified=(current is None or current.get('job-state') in (7,8,9)) if action=='cancel_job' else (current is not None and (current.get('job-state')==4 if action=='hold_job' else current.get('job-state')!=4))
        if not verified:raise RuntimeError('CUPS aceitou o pedido mas o novo estado ainda não foi confirmado. Não repetir automaticamente.')
        return {'verified':True,'action':action,'printer':name,'job_id':job_id}
    def print(self,name,path,copies=1):
        printer_name(name)
        if not self.files:raise Denied('O acesso ao ficheiro não está autorizado.')
        if type(copies)is not int or not 1<=copies<=20:raise Denied('Escolhe entre 1 e 20 cópias.')
        source=self.files.policy.path(path)
        if source.suffix.lower() not in ('.pdf','.txt','.png','.jpg','.jpeg'):raise Denied('A impressão aceita PDF, texto, PNG ou JPEG.')
        target=self.api().printers().get(name)
        if not target:raise Denied('Impressora não encontrada.')
        with tempfile.TemporaryDirectory(prefix='amigo-print-') as directory:
            staged=Path(directory)/('document'+source.suffix.lower())
            with self.files.policy.open_read(str(source)) as src,staged.open('wb') as dst:
                count=0;sha=hashlib.sha256()
                while chunk:=src.read(1024**2):
                    self.check_cancel();count+=len(chunk)
                    if count>512*1024**2:raise Denied('Ficheiro acima de 512 MiB.')
                    sha.update(chunk);dst.write(chunk)
            self.gate.require({'operation':'Enviar documento para impressão','printer':name,'device_uri':target.get('device-uri'),
                               'file':str(source),'bytes':count,'sha256':sha.hexdigest(),'copies':copies,'irreversible':'A impressão pode começar imediatamente.'})
            self.check_cancel();identifier=self.api().print_file(name,staged,copies);job=self.api().job(identifier)
            return {'submitted':True,'job_id':int(identifier),'job_state':job.get('job-state'),'printed':False,
                    'note':'Documento aceite na fila; a impressão física ainda não foi confirmada.'}
