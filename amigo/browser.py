"""On-demand browser process with isolated files/network and a controlled public gateway."""
import configparser
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import stat
import subprocess
import tempfile
import threading
import uuid
from .policy import Denied
from .transactions import Cancelled,Conflict
from .web_policy import browsing_url
from .web_proxy import PublicProxy

class Browser:
    def __init__(self,directory,idle_seconds=90,headless=False):
        self.root=Path(directory);self.idle_seconds=idle_seconds;self.headless=headless
        self.lock=threading.RLock();self.write_lock=threading.Lock();self.process=None;self.proxy=None;self.session=None
        self.pending={};self.ready=threading.Event();self.visible=False;self.active=0;self.timer=None
        self.stderr_bytes=0;self.last_exit=None

    def start(self):
        with self.lock:
            if self.process and self.process.poll() is None:return
            if self.process:self.close()
            self.root.mkdir(parents=True,exist_ok=True,mode=0o700);self.root.chmod(0o700)
            self.session=Path(tempfile.mkdtemp(prefix='session-',dir=self.root));self.ready.clear();self.stderr_bytes=0
            for name in ('profile','downloads','config'): (self.session/name).mkdir(mode=0o700)
            self.theme_config(self.session/'config')
            self.proxy=PublicProxy(self.session/'proxy.sock').start()
            try:
                self.process=subprocess.Popen(self.argv(),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                              env={'PATH':'/usr/bin'},bufsize=0)
            except BaseException:self.close();raise
            process=self.process
            threading.Thread(target=self.read,args=(process,),daemon=True,name='amigo-browser-results').start()
            threading.Thread(target=self.discard_errors,args=(process,),daemon=True,name='amigo-browser-diagnostics').start()
        if not self.ready.wait(20):
            self.close();raise RuntimeError('The isolated browser could not start')
        if self.process is None or self.process.poll() is not None:raise RuntimeError('The isolated browser exited during startup')

    @staticmethod
    def theme_config(destination):
        parser=configparser.ConfigParser(interpolation=None,strict=False);parser.optionxform=str
        source=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'kdeglobals'
        try:parser.read(source)
        except configparser.Error:return
        clean=configparser.ConfigParser(interpolation=None);clean.optionxform=str
        for section in parser.sections():
            if section.startswith('Colors:'):clean[section]=dict(parser[section])
            elif section=='General':clean[section]={k:v for k,v in parser[section].items() if k in ('font','menuFont','toolBarFont','smallestReadableFont','fixed','ColorScheme')}
            elif section=='KDE':clean[section]={'widgetStyle':'Breeze'}
        with (destination/'kdeglobals').open('w') as file:clean.write(file)
        # Copy only selected UI fonts, never mount the personal font/config tree.
        fonts=destination/'fonts';fonts.mkdir(exist_ok=True)
        families={value.split(',',1)[0] for key,value in clean['General'].items() if key.lower().endswith('font')} if clean.has_section('General') else set()
        for index,family in enumerate(sorted(families)):
            try:
                match=subprocess.check_output(['/usr/bin/fc-match','-f','%{file}', '--', family],timeout=3).decode()
                source=Path(match)
                if source.suffix.lower() in ('.ttf','.otf','.ttc') and source.is_file() and source.stat().st_size<32*1024**2:
                    shutil.copyfile(source,fonts/(str(index)+source.suffix))
            except (OSError,subprocess.SubprocessError,UnicodeError):pass
        (destination/'fonts.conf').write_text('<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd"><fontconfig><include>/etc/fonts/fonts.conf</include><dir>/config/fonts</dir><cachedir>/profile/fontcache</cachedir></fontconfig>')

    def argv(self):
        code=Path(__file__).resolve().parent
        args=['/usr/bin/bwrap','--unshare-all','--die-with-parent','--new-session','--cap-drop','ALL',
              '--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib','/lib64',
              '--proc','/proc','--dev','/dev','--tmpfs','/tmp','--tmpfs','/dev/shm',
              '--dir','/home/browser','--dir','/run','--dir','/gateway','--dir','/app',
              '--ro-bind',str(code),'/app/amigo','--ro-bind',str(self.proxy.path),'/gateway/proxy.sock',
              '--bind',str(self.session/'profile'),'/profile','--bind',str(self.session/'downloads'),'/downloads',
              '--ro-bind',str(self.session/'config'),'/config','--dir','/etc',
              '--ro-bind','/etc/ssl','/etc/ssl','--ro-bind','/etc/fonts','/etc/fonts','--clearenv',
              '--setenv','HOME','/home/browser','--setenv','PATH','/usr/bin','--setenv','LANG','C.UTF-8',
              '--setenv','FONTCONFIG_FILE','/config/fonts.conf','--setenv','QT_QPA_PLATFORMTHEME','kde','--setenv','QT_STYLE_OVERRIDE','breeze',
              '--setenv','XDG_CONFIG_HOME','/config','--setenv','XDG_CACHE_HOME','/profile/cache',
              '--setenv','QT_QPA_PLATFORM','offscreen' if self.headless else 'wayland',
              '--setenv','QTWEBENGINE_CHROMIUM_FLAGS',
              '--proxy-server=http://127.0.0.1:18737 --proxy-bypass-list=<-loopback> --disable-quic --disable-background-networking --disable-sync --disable-extensions --disable-component-update --no-first-run --no-default-browser-check --disable-gpu --js-flags=--max-old-space-size=128']
        if not self.headless:
            runtime=Path(os.environ.get('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}'))
            display=os.environ.get('WAYLAND_DISPLAY','wayland-0');source=runtime/display
            if '/' in display or not stat.S_ISSOCK(source.stat().st_mode):raise Denied('Wayland socket unavailable')
            args+=['--dir','/run/browser','--ro-bind',str(source),'/run/browser/wayland-0',
                   '--setenv','XDG_RUNTIME_DIR','/run/browser','--setenv','WAYLAND_DISPLAY','wayland-0']
        else:args+=['--dir','/run/browser','--setenv','XDG_RUNTIME_DIR','/run/browser']
        return args+['--chdir','/app','--','/usr/bin/python','-I','/app/amigo/browser_worker.py']

    def read(self,process):
        try:
            for line in iter(process.stdout.readline,b''):
                if len(line)>2*1024**2:process.kill();break
                try:value=json.loads(line)
                except (ValueError,UnicodeError):continue
                if self.process is not process:continue
                if value.get('event')=='ready':self.ready.set()
                elif value.get('event')=='visibility':
                    with self.lock:self.visible=bool(value.get('visible'));self.arm_idle()
                else:
                    with self.lock:destination=self.pending.get(value.get('id'))
                    if destination:destination.put(value)
        finally:
            process.stdout.close()
            code=process.wait()
            with self.lock:
                if self.process is process:
                    self.last_exit=code;self.ready.set()
                    for destination in self.pending.values():destination.put({'ok':False,'error':'Browser process ended'})

    def discard_errors(self,process):
        try:
            while chunk:=process.stderr.read(4096):self.stderr_bytes+=len(chunk)
        finally:process.stderr.close()

    def send(self,value):
        with self.write_lock:
            if not self.process or self.process.poll() is not None:raise RuntimeError('Browser is not running')
            self.process.stdin.write(json.dumps(value,ensure_ascii=False).encode()+b'\n');self.process.stdin.flush()

    def request(self,operation,arguments=None,cancel=None):
        if operation not in ('navigate','read','click','search','scroll','download','show','hide'):raise Denied('Unknown browser capability')
        args=arguments or {}
        if operation in ('navigate','download'):browsing_url(args['url'])
        identifier=uuid.uuid4().hex;result_queue=queue.Queue()
        with self.lock:
            self.active+=1
            if self.timer:self.timer.cancel();self.timer=None
        try:
            self.start()
            with self.lock:self.pending[identifier]=result_queue
            self.send({'id':identifier,'operation':operation,'arguments':args})
            waited=0
            while waited<200:
                if cancel and cancel.is_set():
                    self.send({'id':identifier,'operation':'cancel'});raise Cancelled('Browser operation cancelled')
                try:result=result_queue.get(timeout=.2)
                except queue.Empty:waited+=.2;continue
                if not result.get('ok'):raise RuntimeError(result.get('error') or 'Browser operation failed')
                return result.get('result')
            self.send({'id':identifier,'operation':'cancel'});raise TimeoutError('Browser response timed out')
        finally:
            with self.lock:self.active-=1;self.pending.pop(identifier,None);self.arm_idle()

    def arm_idle(self):
        if self.timer:self.timer.cancel();self.timer=None
        if self.process and not self.visible and not self.active:
            self.timer=threading.Timer(self.idle_seconds,self.expire);self.timer.daemon=True;self.timer.start()

    def expire(self):
        with self.lock:
            if not self.active and not self.visible:self.close()

    def download(self,url,destination,files):
        target=files.policy.path(destination,exists=False)
        if target.exists():raise Conflict('Download destination already exists')
        # Keep the session alive through verification and delivery, including slow disks.
        with self.lock:
            self.active+=1
            if self.timer:self.timer.cancel();self.timer=None
        source=None
        try:
            name=uuid.uuid4().hex+'.download'
            value=self.request('download',{'url':url,'filename':name},files.cancel)
            source=self.session/'downloads'/name
            if not source.is_file() or source.is_symlink() or source.stat().st_nlink!=1:raise Denied('Invalid staged download')
            with source.open('rb') as file:sha=hashlib.file_digest(file,'sha256').hexdigest()
            if sha!=value['sha256'] or source.stat().st_size!=value['bytes']:raise Conflict('Download verification failed')
            return files.transactions.apply([{'path':target,'staged':source,'expected':None}],files.cancel)|{'bytes':value['bytes'],'sha256':sha}
        finally:
            if source:source.unlink(missing_ok=True)
            with self.lock:self.active-=1;self.arm_idle()

    def close(self):
        with self.lock:
            if self.timer:self.timer.cancel();self.timer=None
            process,self.process=self.process,None
            for destination in self.pending.values():destination.put({'ok':False,'error':'Browser session ended'})
            if process and process.poll() is None:
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
            if process and process.stdin:process.stdin.close()
            if self.proxy:self.proxy.close();self.proxy=None
            if self.session:shutil.rmtree(self.session,ignore_errors=True);self.session=None
            self.visible=False
