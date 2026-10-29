from __future__ import annotations

import hashlib
import http.client
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from app import create_server
from pet.media import MediaStore
from pet.model import PetError

# Signatures are non-character dummy bytes. Browser codec playback is tested separately
# with a real locally generated color-pattern WebM; no SL-001 resource is fabricated.
FAKE_MP4 = b'\x00\x00\x00\x18ftypisom' + bytes(range(32))
FAKE_PNG = b'\x89PNG\r\n\x1a\n' + bytes(range(20))
OWNER_TOKEN = 'O' * 43  # deterministic, isolated test tokens; never used at runtime
BRIDGE_TOKEN = 'B' * 43


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=MediaStore(Path(self.tmp.name))
    def tearDown(self): self.tmp.cleanup()

    def test_preserves_bytes_hash_and_reference_count(self):
        meta=self.store.put('idle_video',FAKE_MP4)
        self.assertEqual(meta['sha256'],hashlib.sha256(FAKE_MP4).hexdigest())
        self.assertEqual(self.store.get('idle_video')[0].read_bytes(),FAKE_MP4)
        self.store.put('happy_video',FAKE_MP4)
        self.store.delete('idle_video')
        self.assertEqual(self.store.get('happy_video')[0].read_bytes(),FAKE_MP4)
        self.store.delete('happy_video')
        self.assertFalse(list(Path(self.tmp.name).glob('*.bin')))

    def test_replaces_without_modifying_original(self):
        self.store.put('idle_poster', FAKE_PNG)
        self.assertEqual(self.store.get('idle_poster')[0].read_bytes(),FAKE_PNG)
        self.store.put('idle_poster',FAKE_PNG+b'different')
        self.assertEqual(len(list(Path(self.tmp.name).glob('*.bin'))),1)

    def test_rejects_invalid_slots_and_content(self):
        with self.assertRaises(PetError): self.store.put('../evil', FAKE_MP4)
        with self.assertRaises(PetError): self.store.put('idle_video',FAKE_PNG)
        with self.assertRaises(PetError): self.store.put('idle_poster',b'not an image')
        with self.assertRaises(PetError): self.store.put('idle_video',b'')


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.server=create_server('127.0.0.1',0,self.tmp.name,owner_token=OWNER_TOKEN,bridge_token=BRIDGE_TOKEN)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.port=self.server.server_port

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()

    def req(self,method,path,body=None,headers=None,*,auth='owner'):
        hdr=dict(headers or {})
        if auth == 'owner': hdr.setdefault('Authorization',f'Bearer {OWNER_TOKEN}')
        if auth == 'bridge': hdr.setdefault('Authorization',f'Bearer {BRIDGE_TOKEN}')
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        conn.request(method,path,body=body,headers=hdr)
        response=conn.getresponse(); content=response.read(); result=(response.status,dict(response.getheaders()),content); conn.close(); return result

    def json_req(self,method,path,body=None,headers=None,*,auth='owner'):
        hdr={'Content-Type':'application/json',**(headers or {})}
        status,h,b=self.req(method,path,None if body is None else json.dumps(body).encode(),hdr,auth=auth)
        return status,json.loads(b)

    def test_static_and_initial_state(self):
        status,headers,body=self.req('GET','/')
        self.assertEqual(status,200); self.assertIn('Meu slime',body.decode())
        self.assertIn("default-src 'self'",headers['Content-Security-Policy'])
        status,data=self.json_req('GET','/api/state')
        self.assertEqual((status,data['state']['petId'],data['state']['xp']),(200,'SL-001',0))
        self.assertEqual(self.req('GET','/../pet/service.py')[0],404)

    def test_head_supports_health_checks_without_body(self):
        status, headers, body = self.req('HEAD','/')
        self.assertEqual(status,200)
        self.assertEqual(body,b'')
        self.assertGreater(int(headers['Content-Length']),0)
        status, _, body = self.req('HEAD','/api/state')
        self.assertEqual((status,body),(200,b''))

    def test_action_persistence_idempotency_and_context(self):
        action={'action':'PLAY','eventId':'id-1'}
        status,result=self.json_req('POST','/api/actions',action)
        self.assertEqual((status,result['xpAwarded']),(200,5))
        self.assertTrue(self.json_req('POST','/api/actions',action)[1]['duplicate'])
        self.json_req('POST','/api/bridge/consent',{'receiveEvents':False,'shareData':True})
        self.assertEqual(self.json_req('GET','/api/bridge/context',auth='bridge')[1]['context']['petId'],'SL-001')
        status,result=self.json_req('POST','/api/actions',{'action':'LEARN','eventId':'id-1'})
        self.assertEqual(status,409)

    def test_chat_text_field_is_rejected_without_mutating_state(self):
        status, _ = self.json_req('POST', '/api/actions', {
            'action': 'CHAT', 'eventId': 'privacy-check', 'meaningful': True,
            'text': 'SYNTHETIC_TEST_TEXT',
        })
        self.assertEqual(status, 400)
        state = self.json_req('GET', '/api/state')[1]['state']
        self.assertEqual((state['xp'], state['happiness'], state['bond'], state['trust']), (0, 75, 20, 50))
        self.assertEqual(self.json_req('GET', '/api/memories')[1]['memories'], [])
        self.assertEqual(self.json_req('GET', '/api/awards')[1]['awards'], [])

    def test_ui_event_cursor_marks_history_boundary(self):
        status, result = self.json_req('GET', '/api/ui/events/cursor')
        self.assertEqual((status, result), (200, {'cursor': 0}))
        self.json_req('POST', '/api/actions', {'action': 'PLAY', 'eventId': 'cursor-play'})
        cursor = self.json_req('GET', '/api/ui/events/cursor')[1]['cursor']
        self.assertGreater(cursor, 0)
        self.assertEqual(self.json_req('GET', f'/api/ui/events?after={cursor}')[1]['events'], [])
        self.json_req('POST', '/api/actions', {'action': 'REST', 'eventId': 'cursor-rest'})
        later = self.json_req('GET', f'/api/ui/events?after={cursor}')[1]['events']
        self.assertTrue(later)
        self.assertEqual(self.json_req('GET', '/api/ui/events/cursor')[1]['cursor'], later[-1]['seq'])

    def test_origin_and_json_type_are_enforced(self):
        action={'action':'PLAY','eventId':'id-1'}
        status,_=self.json_req('POST','/api/actions',action,{'Origin':'https://evil.example'})
        self.assertEqual(status,403)
        status,_=self.json_req('POST','/api/actions',action,{'Origin':f'http://127.0.0.1:{self.port}'})
        self.assertEqual(status,200)
        status,_,_=self.req('POST','/api/actions',b'{}',{'Content-Type':'text/plain'})
        self.assertEqual(status,400)

    def test_original_media_range_and_deletion(self):
        status,_,body=self.req('POST','/api/media/idle_video',FAKE_MP4,{'Content-Type':'video/mp4'})
        self.assertEqual(status,201); self.assertEqual(json.loads(body)['media']['sha256'],hashlib.sha256(FAKE_MP4).hexdigest())
        status,headers,body=self.req('GET','/media/idle_video',headers={'Range':'bytes=2-9'})
        self.assertEqual((status,body),(206,FAKE_MP4[2:10]))
        self.assertEqual(headers['Content-Range'],f'bytes 2-9/{len(FAKE_MP4)}')
        self.assertEqual(self.req('GET','/media/idle_video',headers={'Range':'bytes=10000-'})[0],416)
        self.assertEqual(self.req('DELETE','/api/media/idle_video')[0],200)
        self.assertEqual(self.req('GET','/media/idle_video')[0],404)

    def test_bridge_validates_confirmation(self):
        event={'eventId':'e','eventType':'AGENT_TASK_COMPLETED','timestamp':'2026-10-28T15:00:00-03:00','source':'muse-agent','payload':{'taskId':'t','success':True}}
        self.json_req('POST','/api/bridge/consent',{'receiveEvents':True,'shareData':True})
        status,result=self.json_req('POST','/api/bridge/events',event,auth='bridge')
        self.assertEqual((status,result['xpAwarded']),(200,15))
        self.assertNotIn('state',result)
        self.assertTrue(self.json_req('POST','/api/bridge/events',event,auth='bridge')[1]['duplicate'])
        status,result=self.json_req('GET','/api/events?after=0',auth='bridge')
        self.assertEqual(status,200); self.assertTrue(all(x['eventType'].startswith('PET_') for x in result['events']))

    def test_delete_memories_without_reset(self):
        self.json_req('POST','/api/actions',{'action':'PLAY','eventId':'a'})
        self.assertTrue(self.json_req('GET','/api/memories')[1]['memories'])
        self.assertGreater(self.json_req('DELETE','/api/memories')[1]['deleted'],0)
        self.assertEqual(self.json_req('GET','/api/memories')[1]['memories'],[])
        self.assertEqual(self.json_req('GET','/api/state')[1]['state']['xp'],5)

    def test_memory_award_and_history_pagination(self):
        for i in range(4):
            self.json_req('POST','/api/actions',{'action':'CHAT','eventId':f'chat-{i}','meaningful':True})
            self.json_req('POST','/api/autonomy/run',{'activity':'JOURNAL','eventId':f'journal-{i}'})
        first=self.json_req('GET','/api/memories?limit=2&offset=0')[1]
        second=self.json_req('GET','/api/memories?limit=2&offset=2')[1]
        self.assertEqual(len(first['memories']),2)
        self.assertTrue(first['hasMore'])
        self.assertGreaterEqual(first['total'],8)
        self.assertTrue(set(x['id'] for x in first['memories']).isdisjoint(x['id'] for x in second['memories']))
        awards=self.json_req('GET','/api/awards?limit=1&offset=0')[1]
        self.assertTrue(awards['hasMore'])
        hist=self.json_req('GET','/api/autonomy/history?limit=2&offset=2')[1]
        self.assertEqual(len(hist['history']),2)
        self.assertFalse(hist['hasMore'])

    def test_memory_page_and_total_share_one_snapshot_during_delete(self):
        for i in range(3):
            self.json_req('POST', '/api/actions', {'action':'CHAT', 'eventId':f'memory-snapshot-{i}'})
        before = self.json_req('GET', '/api/memories?limit=100')[1]
        before_total = before['total']
        self.assertGreater(before_total, 0)
        self.assertEqual(len(before['memories']), before_total)

        # Pause the first read transaction after it commits. Another real HTTP
        # client deletes all memories before the GET response is completed.
        # A page+total from one transaction stays internally consistent, even
        # though it is an older snapshot and cannot promise cross-tab freshness.
        repo = self.server.pet_repository
        transaction = repo.transaction
        read_done, proceed = threading.Event(), threading.Event()

        @contextmanager
        def delayed_transaction():
            with transaction() as conn:
                yield conn
            if not read_done.is_set():
                read_done.set()
                if not proceed.wait(4):
                    raise TimeoutError('A exclusão concorrente não terminou.')

        with patch.object(repo, 'transaction', delayed_transaction), ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.json_req, 'GET', '/api/memories?limit=100')
            try:
                self.assertTrue(read_done.wait(4), 'a leitura inicial deve chegar à fronteira')
                status, deleted = self.json_req('DELETE', '/api/memories')
                self.assertEqual((status, deleted['deleted']), (200, before_total))
            finally:
                proceed.set()
            status, result = future.result(timeout=4)
        self.assertEqual(status, 200)
        self.assertEqual((len(result['memories']), result['total'], result['hasMore']), (before_total, before_total, False))
        self.assertEqual(self.json_req('GET', '/api/memories')[1]['total'], 0)

    def test_awards_pagination_total_and_empty_page_are_consistent(self):
        # Four real grants: the first interaction and three meaningful chats.
        for i in range(4):
            status, _ = self.json_req('POST', '/api/actions', {
                'action': 'CHAT', 'eventId': f'page-chat-{i}', 'meaningful': True,
            })
            self.assertEqual(status, 200)
        first = self.json_req('GET', '/api/awards?limit=2&offset=0')[1]
        second = self.json_req('GET', '/api/awards?limit=2&offset=2')[1]
        past_end = self.json_req('GET', '/api/awards?limit=2&offset=999')[1]
        self.assertEqual((first['total'], second['total'], past_end['total']), (4, 4, 4))
        self.assertEqual((len(first['awards']), len(second['awards']), past_end['awards']), (2, 2, []))
        self.assertTrue(first['hasMore'])
        self.assertFalse(second['hasMore'])
        self.assertFalse(past_end['hasMore'])
        ids = lambda page: {(item['eventId'], item['reason']) for item in page['awards']}
        self.assertTrue(ids(first).isdisjoint(ids(second)))
        self.assertEqual(len(ids(first) | ids(second)), 4)

    def test_unknown_or_malformed_inputs(self):
        self.assertEqual(self.json_req('POST','/api/actions',{'action':'OTHER','eventId':'x'})[0],400)
        self.assertEqual(self.req('GET','/api/not-real')[0],404)
        self.assertEqual(self.req('POST','/api/actions',b'{broken',{'Content-Type':'application/json'})[0],400)


if __name__=='__main__': unittest.main()
