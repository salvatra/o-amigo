"""Isolated Chromium interactions against a disposable, explicitly mapped fixture.

Only the test gateway maps fixture.example to the local server; the production
proxy is unchanged and its private-network denial is tested separately.
"""
import http.server
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from amigo.browser import Browser
from amigo.web_proxy import PublicProxy
from amigo.transactions import Cancelled

PAGE=b'''<!doctype html><title>Fixture</title><body><h1>Fixture page</h1>
<a href="/next">Next page</a><button type="button" onclick="document.querySelector('h1').textContent='Clicked safely'">Change heading</button>
<form action="/search"><input type="search" name="q" placeholder="Search fixture"></form>
<form method="post" action="/forbidden"><input name="q" placeholder="Post search"></form>
<form action="/login"><input name="q" placeholder="Account search"><input type="password" name="password"></form>
<script>fetch('/forbidden',{method:'POST',body:'must not arrive'}).catch(()=>{});</script></body>'''
requests=[]
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  requests.append(('GET',self.path))
  if self.path=='/slow':time.sleep(3)
  self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers()
  try:self.wfile.write(PAGE if self.path=='/' else ('<!doctype html><title>Next</title><body>'+self.path+'</body>').encode())
  except BrokenPipeError:pass
 def do_POST(self):requests.append(('POST',self.path));self.send_response(400);self.end_headers()
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
class FixtureProxy(PublicProxy):
 def connect(self,host,port):
  if host!='fixture.example' or port!=80:return super().connect(host,port)
  connection=socket.create_connection(server.server_address)
  with self.lock:self.connections.add(connection)
  return connection
try:
 with tempfile.TemporaryDirectory() as folder,patch('amigo.browser.PublicProxy',FixtureProxy):
  browser=Browser(Path(folder),headless=True)
  try:
   page=browser.request('navigate',{'url':'http://fixture.example/'})
   assert page['title']=='Fixture'
   button=next(e for e in page['elements'] if e['tag']=='button')
   assert browser.request('click',{'id':button['id']})['clicked']
   assert 'Clicked safely' in browser.request('read')['text']
   search=next(e for e in page['elements'] if e['text']=='Search fixture')
   page=browser.request('search',{'id':search['id'],'text':'ação café'})
   assert '/search?q=' in page['url'] and '%C3%A7' in page['url']
   for label in ('Post search','Account search'):
    page=browser.request('navigate',{'url':'http://fixture.example/'})
    field=next(e for e in page['elements'] if e['text']==label)
    try:browser.request('search',{'id':field['id'],'text':'rejected'});raise AssertionError('Unsafe form accepted')
    except RuntimeError as error:assert 'Only public GET search forms' in str(error)
   page=browser.request('navigate',{'url':'http://fixture.example/'})
   link=next(e for e in page['elements'] if e['tag']=='a')
   assert browser.request('click',{'id':link['id']})['url'].endswith('/next')
   cancel=threading.Event();timer=threading.Timer(.2,cancel.set);timer.start()
   try:browser.request('navigate',{'url':'http://fixture.example/slow'},cancel);raise AssertionError('Cancellation failed')
   except Cancelled:pass
   finally:timer.cancel()
   assert browser.request('navigate',{'url':'http://fixture.example/'})['title']=='Fixture'
   assert not any(method=='POST' for method,path in requests),requests
   print(json.dumps({'passed':True,'checks':['link navigation','fixed button action','Portuguese GET search','POST/password form refusal','page POST blocked','cancel and fresh navigation']}))
  finally:browser.close()
finally:server.shutdown();server.server_close()
