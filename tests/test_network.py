from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import threading
import time
import unittest
from PyQt6.QtCore import QCoreApplication
from amigo.network import Stream
from amigo.protocol import request
from amigo.settings import DEFAULTS

APP=QCoreApplication.instance() or QCoreApplication([])

class Server(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        self.server.received=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.send_response(self.server.status);self.send_header('Content-Type','text/event-stream');self.end_headers()
        if self.server.delay:time.sleep(self.server.delay)
        try:
            for data in self.server.fragments:self.wfile.write(data);self.wfile.flush()
        except (BrokenPipeError,ConnectionResetError):pass

def sse(obj):return b'data: '+json.dumps(obj,ensure_ascii=False).encode()+b'\n\n'

class NetworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Server)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def run_stream(self,fragments,status=200,cancel=False):
        self.server.fragments=fragments;self.server.status=status;self.server.delay=.1 if cancel else 0
        stream=Stream(endpoint=f'http://127.0.0.1:{self.server.server_port}/test');result=[]
        stream.finished.connect(lambda *args:result.append(args))
        stream.start('fake-key-never-written',request(DEFAULTS,[{'role':'user','content':'test'}]))
        if cancel:stream.cancel()
        deadline=time.monotonic()+3
        while not result and time.monotonic()<deadline:APP.processEvents();time.sleep(.001)
        self.assertTrue(result);self.assertIsNone(stream.reply);return result[0]
    def test_byte_fragmented_utf8_and_actual_cost(self):
        content=sse({'choices':[{'delta':{'content':'Olá, ação e café.'},'finish_reason':None}]})
        content+=sse({'provider':'fixture','usage':{'cost':.000123},'choices':[{'delta':{},'finish_reason':'stop'}]})+b'data: [DONE]\n\n'
        result=self.run_stream([bytes([byte]) for byte in content])
        self.assertEqual(result[0],'complete');self.assertEqual(result[2]['content'],'Olá, ação e café.')
        self.assertEqual(result[3]['cost'],.000123)
    def test_fragmented_tool_arguments(self):
        chunks=[sse({'choices':[{'delta':{'tool_calls':[{'index':0,'id':'call_1','function':{'name':'read_file','arguments':'{"path":'}}]}}]}),
                sse({'choices':[{'delta':{'tool_calls':[{'index':0,'function':{'arguments':'"/note"}'}}]},'finish_reason':'tool_calls'}]}),b'data: [DONE]\n\n']
        result=self.run_stream(chunks)
        self.assertEqual(result[0],'complete');self.assertEqual(json.loads(result[2]['tool_calls'][0]['function']['arguments']),{'path':'/note'})
    def test_incomplete_stream_never_yields_executable_message(self):
        result=self.run_stream([sse({'choices':[{'delta':{'tool_calls':[{'index':0,'id':'one','function':{'name':'write_file','arguments':'{"path":'}}]}}]})])
        self.assertEqual(result[0],'failed');self.assertIsNone(result[2])
    def test_http_failures_are_safe_and_price_unchanged(self):
        for code in (401,402,404,429,503):
            result=self.run_stream([b'private upstream error body'],status=code)
            self.assertEqual(result[0],'failed');self.assertNotIn('private',result[1])
            self.assertEqual(self.server.received['provider']['max_price'],{'prompt':.3,'completion':1.2})
    def test_cancel(self):
        result=self.run_stream([],cancel=True);self.assertEqual(result[0],'interrupted')
    def test_citations_and_search_usage(self):
        result=self.run_stream([sse({'choices':[{'delta':{'content':'Answer','annotations':[{'type':'url_citation','url_citation':{'url':'https://example.com/doc','title':'Documentation'}}]},'finish_reason':'stop'}],
                                          'usage':{'server_tool_use_details':{'web_search_requests':2}}}),b'data: [DONE]\n\n'])
        self.assertEqual(result[3]['sources'][0]['title'],'Documentation');self.assertEqual(result[3]['searches'],2)
        self.assertNotIn('cost',result[3])

if __name__=='__main__':unittest.main()
