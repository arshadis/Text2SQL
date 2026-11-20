"""Stdlib HTTP server: no external packages required to run in Docker."""
from __future__ import annotations
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from .db import allowed_relations, ro_connection
from .pipeline import answer

ROOT=Path(__file__).resolve().parents[1]
STATIC=ROOT/'static'
FILES={'/':'index.html','/index.html':'index.html','/style.css':'style.css','/app.js':'app.js'}
MIME={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8'}

class Handler(BaseHTTPRequestHandler):
    server_version='FootballText2SQL/0.1'
    def _json(self, obj, code=200):
        body=json.dumps(obj,ensure_ascii=False,default=str).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers();self.wfile.write(body)
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/health':
            return self._json({'status':'ok','database':'readonly'})
        if path=='/api/meta':
            try:
                conn=ro_connection()
                try:
                    counts={'teams':conn.execute('select count(*) from team').fetchone()[0],
                            'players':conn.execute('select count(*) from player').fetchone()[0],
                            'matches':conn.execute('select count(*) from "match"').fetchone()[0]}
                finally:
                    conn.close()
                return self._json({'season':'2026-27','snapshot':'2026-11-01',**counts})
            except Exception: return self._json({'error':'Database unavailable'},503)
        if path not in FILES: return self._json({'error':'Not found'},404)
        src=STATIC/FILES[path]
        try: body=src.read_bytes()
        except OSError: return self._json({'error':'Static resource unavailable'},503)
        self.send_response(200)
        self.send_header('Content-Type',MIME[src.suffix]);self.send_header('Content-Length',str(len(body)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(body)
    def do_POST(self):
        if urlparse(self.path).path!='/api/ask': return self._json({'error':'Not found'},404)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<1 or size>8192:return self._json({'error':'Request body size invalid'},413)
            obj=json.loads(self.rfile.read(size))
            if not isinstance(obj,dict) or not isinstance(obj.get('question'),str):
                return self._json({'error':'Question must be text'},400)
            state=obj.get('state')
            prev=state.get('pending_question') if isinstance(state,dict) else None
            return self._json(answer(obj['question'],previous_question=prev))
        except (ValueError,UnicodeDecodeError): return self._json({'error':'Invalid JSON'},400)
        except Exception:
            # Never print secret, SQL or a raw upstream response into a public page.
            return self._json({'error':'Internal error'},500)
    def log_message(self, fmt, *args):
        # Avoid logging user questions or authentication headers.
        print(f'http {self.address_string()} '+(fmt%args),flush=True)


def main():
    port=int(os.environ.get('PORT','3000'))
    server=ThreadingHTTPServer(('0.0.0.0',port),Handler)
    print(f'Football Text-to-SQL: http://localhost:{port}',flush=True)
    server.serve_forever()

if __name__=='__main__':main()
