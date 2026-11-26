"""Real HTTP tests, no external provider required."""
import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from app.server import Handler

class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.port=cls.server.server_address[1]
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=2)
    def request(self,method,path,payload=None):
        conn=HTTPConnection('127.0.0.1',self.port,timeout=5)
        body=None if payload is None else json.dumps(payload,ensure_ascii=False).encode('utf-8')
        conn.request(method,path,body=body,headers={'Content-Type':'application/json'} if body else {})
        r=conn.getresponse();content=r.read();status=r.status
        conn.close();return status,json.loads(content) if path not in ('/','/style.css','/app.js') else content
    def test_health(self):
        s,b=self.request('GET','/health');self.assertEqual(s,200);self.assertEqual(b['database'],'readonly')
    def test_meta(self):
        s,b=self.request('GET','/api/meta');self.assertEqual(s,200)
        self.assertEqual((b['teams'],b['players'],b['matches']),(18,531,306))
        from app.source_fingerprint import pipeline_sha256
        self.assertEqual(b.get('pipeline_sha256'),pipeline_sha256())
    def test_write_request_cannot_execute(self):
        s,b=self.request('POST','/api/ask',{'question':'Delete all cancelled matches'})
        self.assertEqual(s,200);self.assertEqual(b['action'],'refuse_write');self.assertIsNone(b['sql'])
        self.assertFalse(b['database_executed'])
    def test_bad_request(self):
        s,b=self.request('POST','/api/ask',{'not_question':1});self.assertEqual(s,400)

if __name__=='__main__':unittest.main()
