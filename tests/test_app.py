"""ASGI integration tests; no external services, test client package or network required."""
import asyncio
import importlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.pop('SKIPRO_MODEL', None)
from app import main
from app.services import analyze_gsc, make_plan, model_plan


async def request(method, path, body=None, cookie=None, headers=None, query=b''):
    raw = json.dumps(body).encode() if isinstance(body, dict) else body or b''
    sent = []
    hs = [(b'host', b'testserver')]
    if isinstance(body, dict): hs.append((b'content-type', b'application/json'))
    if cookie: hs.append((b'cookie', cookie.encode()))
    hs += [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,'scheme':'http',
             'path':path,'raw_path':path.encode(),'query_string':query,'headers':hs,'client':('127.0.0.1',1),'server':('testserver',80)}
    delivered = False
    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {'type':'http.request','body':raw,'more_body':False}
        await asyncio.sleep(60)
        return {'type':'http.disconnect'}
    async def send(message): sent.append(message)
    await main.app(scope, receive, send)
    start = next(m for m in sent if m['type']=='http.response.start')
    data = b''.join(m.get('body',b'') for m in sent if m['type']=='http.response.body')
    response_headers = dict(start['headers'])
    return start['status'], data, response_headers


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_data = main.DATA
        main.DATA = Path(self.temp.name)
        main.init_db()
        status, _, headers = self.req('GET', '/api/health')
        self.cookie = headers[b'set-cookie'].decode().split(';')[0]
    def tearDown(self):
        main.DATA = self.old_data
        self.temp.cleanup()
    def req(self, *args, **kwargs): return asyncio.run(request(*args, **kwargs))
    def create_plan(self):
        status, raw, _ = self.req('POST','/api/plans',{'sport':'ski','level':'beginner','minutes':45,'goal':'More control'},cookie=self.cookie)
        self.assertEqual(status,201)
        return json.loads(raw)

    def test_plan_saved_across_connections_and_isolated(self):
        p = self.create_plan()
        self.assertEqual(sum(x['minutes'] for x in p['blocks']),45)
        self.assertEqual(p['source'],'rules')
        self.assertEqual(len(json.loads(self.req('GET','/api/plans',cookie=self.cookie)[1])['items']),1)
        self.assertEqual(json.loads(self.req('GET','/api/plans')[1])['items'],[])
        main.init_db()  # restart-style initialization must not reset data
        self.assertEqual(len(json.loads(self.req('GET','/api/plans',cookie=self.cookie)[1])['items']),1)

    def test_validation_and_cross_origin(self):
        self.assertEqual(self.req('POST','/api/plans',{'minutes':1})[0],422)
        self.assertEqual(self.req('POST','/api/plans',{'level':'expert'})[0],422)
        self.assertEqual(self.req('POST','/api/plans',{},headers={'Origin':'https://untrusted.example'})[0],403)

    def test_logs_export_and_ownership(self):
        p = self.create_plan()
        body = {'plan_id':p['id'],'date':'2026-10-15','minutes':30,'effort':4,'note':'=1+1'}
        self.assertEqual(self.req('POST','/api/logs',body)[0],404)
        self.assertEqual(self.req('POST','/api/logs',body,cookie=self.cookie)[0],201)
        logs = json.loads(self.req('GET','/api/logs',cookie=self.cookie)[1])
        self.assertEqual(logs['total_minutes'],30)
        export = self.req('GET','/api/logs/export',cookie=self.cookie)[1].decode()
        self.assertIn("'=1+1",export)

    def test_upload_delete_limits_and_isolation(self):
        self.assertEqual(self.req('POST','/api/videos',b'not-a-video',cookie=self.cookie)[0],415)
        raw = b'\x00\x00\x00\x18ftypisom' + b'\0'*20
        status, b, _ = self.req('POST','/api/videos',raw,cookie=self.cookie,query=b'filename=..%2Fclip.mp4')
        self.assertEqual(status,201)
        video = json.loads(b)
        self.assertEqual(video['filename'],'clip.mp4')
        self.assertEqual(self.req('POST','/api/videos/'+video['id']+'/inspect')[0],404)
        self.assertEqual(self.req('DELETE','/api/videos/'+video['id'],cookie=self.cookie)[0],204)
        self.assertFalse(list((main.DATA/'uploads').iterdir()))
        with patch.object(main,'MAX_VIDEO',5):
            self.assertEqual(self.req('POST','/api/videos',raw,cookie=self.cookie)[0],413)

    def test_video_decoder_rejects_header_only_file(self):
        raw=b'\x00\x00\x00\x18ftypisom'+b'\0'*20
        p=json.loads(self.req('POST','/api/videos',raw,cookie=self.cookie)[1])
        status=self.req('POST','/api/videos/'+p['id']+'/inspect',cookie=self.cookie)[0]
        self.assertIn(status,[422,503])

    def test_valid_video_metadata_when_opencv_available(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest('Optional OpenCV is not installed')
        path=main.DATA/'test.mp4'
        writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),10,(64,48))
        if not writer.isOpened(): self.skipTest('MP4 encoder unavailable')
        for _ in range(20): writer.write(np.zeros((48,64,3),dtype=np.uint8))
        writer.release()
        p=json.loads(self.req('POST','/api/videos',path.read_bytes(),cookie=self.cookie)[1])
        status,b,_=self.req('POST','/api/videos/'+p['id']+'/inspect',cookie=self.cookie)
        self.assertEqual(status,200)
        d=json.loads(b)
        self.assertEqual((d['width'],d['height']),(64,48))
        self.assertAlmostEqual(d['duration_seconds'],2)
        self.assertEqual(d['analysis_type'],'metadata-only')

    def test_gsc_aggregation_zero_and_bad_values(self):
        d=analyze_gsc('Query,Clicks,Impressions,Position\na,1,100,10\na,9,900,2\nb,0,0,5')
        self.assertAlmostEqual(d['ctr'],.01)
        self.assertEqual(d['queries'][0]['position'],2.8)
        self.assertIsNone(d['queries'][1]['position'])
        for text in ['Query,Clicks,Impressions,Position\na,2,1,2','Query,Clicks,Impressions,Position\na,1,100,nan','no,headers\na,2']:
            self.assertEqual(self.req('POST','/api/seo/analyze',{'csv':text})[0],422)
        self.assertEqual(json.loads(self.req('GET','/api/seo/sample')[1])['source'],'synthetic-demo')

    def test_guides_and_local_robots(self):
        for article in main.articles():
            s,b,h=self.req('GET','/guides/'+article['slug'])
            self.assertEqual(s,200)
            self.assertIn(article['title'].encode(),b)
            self.assertEqual(h[b'x-robots-tag'],b'noindex, nofollow')
        self.assertEqual(self.req('GET','/guides/no-such-guide')[0],404)
        self.assertIn(b'Disallow: /',self.req('GET','/robots.txt')[1])
        with patch.object(main,'PUBLIC_URL','https://ski.example'):
            self.assertIn(b'https://ski.example/guides/',self.req('GET','/sitemap.xml')[1])
            self.assertIn(b'rel="canonical"',self.req('GET','/guides')[1])

    def test_ollama_success_and_explicit_fallback(self):
        p={'sport':'ski','level':'beginner','minutes':30,'goal':'Control'}
        template=make_plan(p)
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self,*args): return json.dumps({'message':{'content':json.dumps({'summary':'Practice familiar movements with your instructor.'})}}).encode()
        with patch.dict(os.environ,{'SKIPRO_MODEL':'test-model'}):
            with patch('urllib.request.urlopen',return_value=FakeResponse()):
                self.assertEqual(model_plan(p,template)['source'],'ollama')
            with patch('urllib.request.urlopen',side_effect=OSError('Offline')):
                d=model_plan(p,template)
                self.assertEqual(d['source'],'rules')
                self.assertIn('notice',d)


if __name__=='__main__': unittest.main()
