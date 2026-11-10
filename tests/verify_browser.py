"""Real isolated Chromium/public-network smoke test; no key or personal profile."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from amigo.browser import Browser
from amigo.policy import Policy,Denied
from amigo.transactions import Transactions
from amigo.files import Files

with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);data=root/'data';data.mkdir();policy=Policy([data]);tx=Transactions(root/'recovery',policy);files=Files(policy,tx)
    browser=Browser(root/'browser',idle_seconds=1,headless=True)
    try:
        page=browser.request('navigate',{'url':'https://example.com'})
        assert page['title']=='Example Domain' and page['elements']
        assert browser.request('read')['url'].startswith('https://example.com')
        assert browser.request('scroll',{'pages':1})['scrolled']
        for url in ('http://127.0.0.1','file:///etc/passwd','https://example.com/login'):
            try:browser.request('navigate',{'url':url});raise AssertionError('Unsafe URL was accepted')
            except Denied:pass
        # Probe the exact namespace configuration with a fixed diagnostic program.
        argv=browser.argv();argv=argv[:argv.index('--')+1]
        probe='''import os,socket,json,pathlib
direct=False
try:
 socket.create_connection(('1.1.1.1',443),timeout=1).close();direct=True
except OSError:pass
print(json.dumps({'direct_network':direct,'host_home':pathlib.Path(HOST).exists(),'session_bus':'DBUS_SESSION_BUS_ADDRESS' in os.environ,'key':'OPENROUTER_API_KEY' in os.environ}))
'''.replace('HOST',repr(str(Path.home())))
        isolated=json.loads(subprocess.check_output(argv+['/usr/bin/python','-c',probe],env={'PATH':'/usr/bin','OPENROUTER_API_KEY':'synthetic-sentinel'}))
        assert isolated=={'direct_network':False,'host_home':False,'session_bus':False,'key':False},isolated
        result=browser.download('https://example.com',str(data/'download.html'),files)
        assert result['bytes']>0 and hashlib.sha256((data/'download.html').read_bytes()).hexdigest()==result['sha256']
        browser.request('show');time.sleep(1.3);assert browser.process and browser.process.poll() is None
        browser.request('hide');deadline=time.monotonic()+5
        while browser.process and time.monotonic()<deadline:time.sleep(.05)
        assert browser.process is None,'Hidden idle browser remained resident'
        print(json.dumps({'passed':True,'checks':['real HTTPS via gateway','page extraction','scroll','blocked local/file/account URLs','no host home/session bus/key/direct network','verified staged download','visible session retained','hidden idle teardown']}))
    finally:browser.close();tx.close()
