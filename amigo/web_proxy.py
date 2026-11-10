"""Unix-socket HTTP CONNECT gateway. DNS is validated and pinned before connecting.

The browser's network namespace reaches this socket through a loopback bridge.
There is no DNS or host-network access in the browser namespace itself.
"""
import os
from pathlib import Path
import selectors
import socket
import threading
import time
from .policy import Denied
from .web_policy import parse_url,resolve_public,public_ip

def relay(left,right,max_bytes=2*1024**3,timeout=120):
    selector=selectors.DefaultSelector();total=0;deadline=time.monotonic()+timeout
    for source,target in ((left,right),(right,left)):
        source.settimeout(15);target.settimeout(15);selector.register(source,selectors.EVENT_READ,target)
    try:
        while selector.get_map():
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Proxy connection lifetime exceeded')
            events=selector.select(min(30,remaining))
            if not events:return
            for key,_ in events:
                data=key.fileobj.recv(65536)
                if not data:return
                total+=len(data)
                if total>max_bytes:raise Denied('Proxy transfer limit exceeded')
                key.data.sendall(data)
    finally:selector.close()

def read_headers(connection):
    data=bytearray()
    while b'\r\n\r\n' not in data:
        chunk=connection.recv(4096)
        if not chunk:raise ValueError('Incomplete HTTP headers')
        data.extend(chunk)
        if len(data)>32768:raise ValueError('HTTP header limit exceeded')
    head,_,tail=bytes(data).partition(b'\r\n\r\n')
    return head.decode('ascii'),tail

class PublicProxy:
    def __init__(self,path):
        self.path=Path(path);self.listener=None;self.thread=None;self.stopped=threading.Event()
        self.connections=set();self.lock=threading.Lock();self.slots=threading.BoundedSemaphore(48)

    def start(self):
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.listener.bind(str(self.path));os.chmod(self.path,0o600);self.listener.listen(16)
        self.thread=threading.Thread(target=self.accept,name='amigo-web-gateway',daemon=True);self.thread.start()
        return self

    def accept(self):
        while not self.stopped.is_set():
            try:connection,_=self.listener.accept()
            except OSError:return
            if self.stopped.is_set():connection.close();return
            if not self.slots.acquire(blocking=False):connection.close();continue
            with self.lock:self.connections.add(connection)
            threading.Thread(target=self.handle,args=(connection,),daemon=True).start()

    def connect(self,host,port):
        last=None
        for family,kind,protocol,_,address in resolve_public(host,port):
            target=socket.socket(family,kind,protocol);target.settimeout(10)
            try:
                target.connect(address)
                if not public_ip(target.getpeername()[0]):raise Denied('Peer address is not public')
                with self.lock:self.connections.add(target)
                return target
            except (OSError,Denied) as error:last=error;target.close()
        raise OSError('Public destination is unavailable') from last

    def handle(self,connection):
        target=None;established=False
        try:
            connection.settimeout(10);head,tail=read_headers(connection)
            lines=head.split('\r\n');method,url,version=lines[0].split(' ')
            if version not in ('HTTP/1.0','HTTP/1.1'):raise Denied('Unsupported HTTP version')
            if method=='CONNECT':
                parsed,host,port=parse_url('https://'+url)
                if parsed.path or parsed.query or parsed.fragment:raise Denied('Invalid CONNECT authority')
                target=self.connect(host,port)
                connection.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n');established=True
                if tail:target.sendall(tail)
            elif method in ('GET','HEAD'):
                parsed,host,port=parse_url(url)
                if parsed.scheme!='http':raise Denied('Use CONNECT for HTTPS')
                target=self.connect(host,port)
                path=(parsed.path or '/')+('?' + parsed.query if parsed.query else '')
                headers=[]
                for line in lines[1:]:
                    if ':' not in line or line[0].isspace():raise Denied('Invalid HTTP header')
                    name,value=line.split(':',1)
                    if name.lower() in ('host','proxy-authorization','proxy-connection','authorization','connection','content-length','transfer-encoding'):continue
                    headers.append(name+':'+value)
                authority=('['+host+']') if ':' in host else host
                if port!=80:authority+=':'+str(port)
                request=f'{method} {path} HTTP/1.1\r\nHost: {authority}\r\nConnection: close\r\n'+'\r\n'.join(headers)+'\r\n\r\n'
                if tail:raise Denied('Request bodies are not permitted')
                target.sendall(request.encode('ascii'));established=True
            else:raise Denied('HTTP method is not permitted')
            relay(connection,target)
        except (ValueError,OSError,TimeoutError,UnicodeError):
            if not established:
                try:connection.sendall(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
                except OSError:pass
        finally:
            for item in (connection,target):
                if item:
                    with self.lock:self.connections.discard(item)
                    item.close()
            self.slots.release()

    def close(self):
        self.stopped.set()
        if self.listener:
            try:self.listener.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            self.listener.close()
        with self.lock:connections=list(self.connections)
        for connection in connections:
            try:connection.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            connection.close()
        if self.thread:self.thread.join(timeout=2)
        try:self.path.unlink()
        except FileNotFoundError:pass
