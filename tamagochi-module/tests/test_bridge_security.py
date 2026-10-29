from __future__ import annotations

import contextlib
import http.client
import json
import os
import queue
import re
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from app import create_server
from pet.bridge import BridgePolicy, MusePetBridge
from pet.model import PetError
from pet.security import AuthenticationError, OwnerSessions, SESSION_SECONDS

ROOT = Path(__file__).resolve().parents[1]
OWNER = 'O' * 43
BRIDGE = 'B' * 43
OTHER = 'X' * 43
EVENT = {
    'eventId': 'security-event-1', 'eventType': 'AGENT_TASK_COMPLETED',
    'timestamp': '2026-10-28T15:00:00-03:00', 'source': 'test-producer',
    'payload': {'taskId': 'security-task', 'success': True},
}


class BridgeHttpSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.start_server()

    def start_server(self, owner=OWNER, bridge=BRIDGE):
        self.server = create_server('127.0.0.1', 0, self.tmp.name,
                                    owner_token=owner, bridge_token=bridge)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive())

    def tearDown(self):
        self.stop_server()
        self.tmp.cleanup()

    def request(self, method, path, *, body=None, token=None, headers=None):
        headers = dict(headers or {})
        if token is not None:
            headers['Authorization'] = f'Bearer {token}'
        if body is not None:
            headers.setdefault('Content-Type', 'application/json')
            body = json.dumps(body).encode('utf-8')
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers)
            res = conn.getresponse()
            content = res.read()
            return res.status, dict(res.getheaders()), json.loads(content) if content else None
        finally:
            conn.close()

    def set_consent(self, receive=False, share=False, token=OWNER):
        return self.request('POST', '/api/bridge/consent', token=token,
                            body={'receiveEvents': receive, 'shareData': share})

    def login(self, key=OWNER):
        return self.request('POST', '/api/session', body={'token': key},
                            headers={'Origin': f'http://127.0.0.1:{self.port}', 'X-Pet-Request': '1'})

    def test_default_off_denies_bridge_reads_and_writes_without_side_effects(self):
        self.assertEqual(self.request('GET', '/api/bridge/consent', token=OWNER)[2]['consent'],
                         {'receiveEvents': False, 'shareData': False})
        for method, path, body in [('POST', '/api/bridge/events', EVENT),
                                   ('GET', '/api/bridge/context', None),
                                   ('GET', '/api/events', None),
                                   ('HEAD', '/api/events', None)]:
            with self.subTest(method=method, path=path):
                self.assertEqual(self.request(method, path, body=body, token=BRIDGE)[0], 403)
        self.assertEqual(self.server.pet_engine.snapshot(run_due=False)['xp'], 0)
        self.assertEqual(self.server.pet_engine.events(), [])
        with contextlib.closing(self.server.pet_repository.connect()) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM processed_events').fetchone()[0], 0)
        with patch.object(self.server.RequestHandlerClass, '_body', side_effect=AssertionError('must not read body')):
            self.assertEqual(self.request('POST', '/api/bridge/events', body=EVENT, token=BRIDGE)[0], 403)

    def test_revocation_does_not_wait_for_slow_http_body(self):
        self.assertEqual(self.set_consent(True, False)[0], 200)
        reading = threading.Event()
        handler = self.server.RequestHandlerClass
        original = handler._body
        def tracked_body(instance, *args, **kwargs):
            if instance.path == '/api/bridge/events': reading.set()
            return original(instance, *args, **kwargs)
        with patch.object(handler, '_body', tracked_body):
            with socket.create_connection(('127.0.0.1', self.port), timeout=5) as client:
                client.sendall((f'POST /api/bridge/events HTTP/1.0\r\nHost: 127.0.0.1:{self.port}\r\n'
                                f'Authorization: Bearer {BRIDGE}\r\nContent-Type: application/json\r\n'
                                'Content-Length: 2\r\n\r\n').encode('ascii'))
                self.assertTrue(reading.wait(3))
                self.assertEqual(self.set_consent(False, False)[0], 200)
                client.sendall(b'{}')
                self.assertIn(b' 403 ', client.recv(4096))
        self.assertEqual(self.server.pet_engine.snapshot(run_due=False)['xp'], 0)

    def test_authentication_and_role_separation_cover_all_sensitive_routes(self):
        self.assertEqual(self.set_consent(True, True)[0], 200)
        owner_paths = ['/api/state', '/api/config', '/api/memories', '/api/awards',
                       '/api/ui/events', '/api/ui/events/cursor', '/api/bridge/consent', '/api/media', '/media/idle_video']
        for path in owner_paths:
            with self.subTest(path=path):
                self.assertEqual(self.request('GET', path)[0], 401)
                self.assertEqual(self.request('GET', path, token=OTHER)[0], 401)
                self.assertEqual(self.request('GET', path, token=BRIDGE)[0], 401)
        self.assertEqual(self.request('GET', '/api/state', token=OWNER)[0], 200)
        for method, path, body in [('POST', '/api/bridge/events', EVENT),
                                   ('POST', '/%61pi/bridge/events', EVENT),
                                   ('GET', '/api/bridge/context', None), ('GET', '/api/events', None)]:
            with self.subTest(path=path):
                self.assertEqual(self.request(method, path, body=body, token=OWNER)[0], 401)
                self.assertEqual(self.request(method, path, body=body)[0], 401)
                self.assertEqual(self.request(method, path, body=body, token=OTHER)[0], 401)
        self.assertEqual(self.set_consent(False, False, token=BRIDGE)[0], 401)
        self.assertEqual(self.request('POST', '/api/actions', body={'action':'PLAY','eventId':'x'})[0], 401)
        self.assertEqual(self.request('GET', '/api/state?token='+OWNER)[0], 401)

    def test_independent_consent_scopes_minimal_ack_and_revocation(self):
        self.assertEqual(self.set_consent(True, False)[0], 200)
        status, _, result = self.request('POST', '/api/bridge/events', body=EVENT, token=BRIDGE)
        self.assertEqual(status, 200)
        self.assertEqual(result, {'duplicate': False, 'duplicateKind': None, 'xpAwarded': 15})
        self.assertNotIn('state', result)
        self.assertEqual(self.request('GET', '/api/bridge/context', token=BRIDGE)[0], 403)
        self.assertEqual(self.request('GET', '/api/events', token=BRIDGE)[0], 403)
        self.assertEqual(self.set_consent(False, True)[0], 200)
        self.assertEqual(self.request('POST', '/api/bridge/events', body=EVENT, token=BRIDGE)[0], 403)
        status, _, result = self.request('GET', '/api/bridge/context', token=BRIDGE)
        self.assertEqual((status, result['context']['petId']), (200, 'SL-001'))
        self.assertEqual(self.request('GET', '/api/events', token=BRIDGE)[0], 200)
        self.assertEqual(self.set_consent(False, False)[0], 200)
        self.assertEqual(self.request('GET', '/api/bridge/context', token=BRIDGE)[0], 403)
        self.assertEqual(self.set_consent(True, False)[0], 200)
        status, _, result = self.request('POST', '/api/bridge/events', body=EVENT, token=BRIDGE)
        self.assertEqual((status, result['duplicate'], result['xpAwarded']), (200, True, 0))

    def test_consent_requires_owner_and_exact_explicit_booleans(self):
        for body in ({'receiveEvents': True}, {'receiveEvents': 1, 'shareData': False},
                     {'receiveEvents': True, 'shareData': True, 'extra': True},
                     {'receiveEvents': 'true', 'shareData': False}):
            self.assertEqual(self.request('POST', '/api/bridge/consent', token=OWNER, body=body)[0], 400)
        self.assertEqual(self.set_consent(True, True, token=BRIDGE)[0], 401)
        self.assertEqual(self.request('GET', '/api/bridge/consent', token=OWNER)[2]['consent'],
                         {'receiveEvents': False, 'shareData': False})

    def test_origin_host_cors_and_forwarded_host_spoofing(self):
        good = f'http://127.0.0.1:{self.port}'
        status, headers, _ = self.request('GET', '/api/state', token=OWNER, headers={'Origin': good})
        self.assertEqual(status, 200)
        self.assertFalse(any(k.lower().startswith('access-control-allow') for k in headers))
        self.assertEqual(headers['X-Frame-Options'], 'DENY')
        self.assertEqual(self.request('GET', '/api/state', token=OWNER, headers={'Origin':'https://evil.example'})[0], 403)
        for origin in ('null', 'https://evil.example', 'http://localhost:'+str(self.port),
                       'http://127.0.0.1:1', 'http://user@127.0.0.1:'+str(self.port)):
            with self.subTest(origin=origin):
                status, headers, _ = self.request('POST', '/api/actions', token=OWNER,
                    headers={'Origin': origin, 'X-Forwarded-Host': 'evil.example'},
                    body={'action':'PLAY','eventId':'attack'})
                self.assertEqual(status, 403)
                self.assertFalse(any(k.lower().startswith('access-control-allow') for k in headers))
        for host in (f'evil.example:{self.port}', f'localhost.evil.example:{self.port}',
                     f'127.0.0.1:{self.port+1}', f'user@127.0.0.1:{self.port}'):
            self.assertEqual(self.request('GET', '/api/state', token=OWNER, headers={'Host': host})[0], 403)
        status, headers, _ = self.request('OPTIONS', '/api/state', headers={'Origin': 'https://evil.example'})
        self.assertEqual(status, 403)
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        self.assertEqual(self.server.pet_engine.snapshot(run_due=False)['xp'], 0)

    def test_duplicate_host_and_authorization_headers_are_rejected(self):
        for name, values, expected in [('Host', [f'127.0.0.1:{self.port}', f'127.0.0.1:{self.port}'], 403),
                                       ('Authorization', [f'Bearer {OWNER}', f'Bearer {OWNER}'], 401)]:
            with self.subTest(header=name):
                conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
                try:
                    conn.putrequest('GET', '/api/state', skip_host=True)
                    if name != 'Host': conn.putheader('Host', f'127.0.0.1:{self.port}')
                    for value in values: conn.putheader(name, value)
                    if name != 'Authorization': conn.putheader('Authorization', f'Bearer {OWNER}')
                    conn.endheaders()
                    response = conn.getresponse()
                    response.read()
                    self.assertEqual(response.status, expected)
                finally:
                    conn.close()

    def test_owner_session_csrf_login_logout_and_bridge_cannot_use_cookie(self):
        origin = f'http://127.0.0.1:{self.port}'
        self.assertFalse(self.request('GET', '/api/session', headers={'X-Pet-Request':'1'})[2]['authenticated'])
        self.assertEqual(self.request('POST', '/api/session', body={'token':OWNER})[0], 403)
        self.assertEqual(self.login(OTHER)[0], 401)
        status, headers, result = self.login()
        self.assertEqual((status, result), (200, {'authenticated': True}))
        cookie = headers['Set-Cookie']
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Strict', cookie)
        self.assertNotIn(OWNER, cookie)
        cookie = cookie.split(';', 1)[0]
        session_headers = {'Cookie':cookie, 'X-Pet-Request':'1'}
        self.assertEqual(self.request('GET', '/api/state', headers={'Cookie':cookie})[0], 403)
        self.assertEqual(self.request('GET', '/api/state', headers=session_headers)[0], 200)
        self.assertEqual(self.request('GET', '/api/state', headers=session_headers, token=BRIDGE)[0], 401)
        self.assertEqual(self.request('POST', '/api/actions', body={'action':'PLAY','eventId':'x'}, headers=session_headers)[0], 403)
        session_headers['Origin'] = origin
        self.assertEqual(self.request('POST', '/api/actions', body={'action':'PLAY','eventId':'x'}, headers=session_headers)[0], 200)
        self.assertEqual(self.set_consent(True, True)[0], 200)
        self.assertEqual(self.request('GET', '/api/bridge/context', headers=session_headers)[0], 401)
        self.assertEqual(self.request('DELETE', '/api/session', headers=session_headers)[0], 200)
        self.assertEqual(self.request('GET', '/api/state', headers=session_headers)[0], 401)
        self.assertEqual(self.request('GET', '/api/bridge/context', token=BRIDGE)[0], 403)

    def test_restart_forgets_consent_sessions_and_old_credentials_but_keeps_pet(self):
        self.assertEqual(self.set_consent(True, True)[0], 200)
        self.assertEqual(self.request('POST', '/api/bridge/events', body=EVENT, token=BRIDGE)[0], 200)
        status, headers, _ = self.login()
        self.assertEqual(status, 200)
        cookie = headers['Set-Cookie'].split(';',1)[0]
        self.stop_server()
        self.start_server(owner='N'*43, bridge='M'*43)
        self.assertEqual(self.request('GET', '/api/state', token=OWNER)[0], 401)
        self.assertEqual(self.request('GET', '/api/state', headers={'Cookie':cookie,'X-Pet-Request':'1'})[0], 401)
        self.assertEqual(self.request('GET', '/api/bridge/context', token=BRIDGE)[0], 401)
        self.assertEqual(self.request('GET', '/api/bridge/context', token='M'*43)[0], 403)
        self.assertEqual(self.request('GET', '/api/state', token='N'*43)[2]['state']['xp'], 15)

    def test_credentials_and_query_strings_do_not_enter_access_logs(self):
        with self.assertLogs('pet.http', level='INFO') as captured:
            self.login()
            self.request('GET', '/api/state?private-query=do-not-log', token=OWNER)
        output = '\n'.join(captured.output)
        self.assertNotIn(OWNER, output)
        self.assertNotIn(BRIDGE, output)
        self.assertNotIn('do-not-log', output)


class BridgePolicyTests(unittest.TestCase):
    def test_direct_adapter_requires_key_and_consent_before_calling_service(self):
        class Spy:
            called = False
            def process_muse_event(self, event):
                self.called = True
                return {'duplicate': False, 'duplicateKind': None, 'xpAwarded': 15, 'state': {'secret': 1}}
        service = Spy()
        policy = BridgePolicy(BRIDGE)
        bridge = MusePetBridge(service, policy)
        with self.assertRaises(AuthenticationError): bridge.receive(EVENT)
        with self.assertRaises(AuthenticationError): bridge.receive(EVENT, credential=OWNER)
        with self.assertRaises(PermissionError): bridge.receive(EVENT, credential=BRIDGE)
        self.assertFalse(service.called)
        policy.set_consent({'receiveEvents': True, 'shareData': False})
        self.assertEqual(bridge.receive(EVENT, credential=BRIDGE),
                         {'duplicate': False, 'duplicateKind': None, 'xpAwarded': 15})
        with self.assertRaises(PermissionError): bridge.context(credential=BRIDGE)
        with self.assertRaises(PetError): policy.set_consent({'receiveEvents': 'yes', 'shareData': False})
        policy.set_consent({'receiveEvents': False, 'shareData': False})
        with self.assertRaises(PermissionError): bridge.receive(EVENT, credential=BRIDGE)

    def test_revocation_waits_for_inflight_bridge_operation(self):
        entered, release, revoked = threading.Event(), threading.Event(), threading.Event()
        class BlockingService:
            def process_muse_event(self, event):
                entered.set()
                if not release.wait(5): raise RuntimeError('test timeout')
                return {'duplicate': False, 'duplicateKind': None, 'xpAwarded': 15}
        policy = BridgePolicy(BRIDGE)
        policy.set_consent({'receiveEvents': True, 'shareData': False})
        bridge = MusePetBridge(BlockingService(), policy)
        def revoke():
            policy.set_consent({'receiveEvents': False, 'shareData': False})
            revoked.set()
        with ThreadPoolExecutor(max_workers=2) as executor:
            operation = executor.submit(bridge.receive, EVENT, credential=BRIDGE)
            try:
                self.assertTrue(entered.wait(3))
                revocation = executor.submit(revoke)
                self.assertFalse(revoked.wait(0.1))
            finally:
                release.set()
            self.assertEqual(operation.result(timeout=3)['xpAwarded'], 15)
            revocation.result(timeout=3)
        with self.assertRaises(PermissionError): bridge.receive(EVENT, credential=BRIDGE)

    def test_consent_expires_automatically(self):
        now = [100.0]
        policy = BridgePolicy(BRIDGE, clock=lambda: now[0])
        policy.set_consent({'receiveEvents': True, 'shareData': True})
        with policy.authorized(BRIDGE, 'receiveEvents'):
            pass
        now[0] += SESSION_SECONDS
        with self.assertRaises(PermissionError):
            with policy.authorized(BRIDGE, 'receiveEvents'):
                pass
        self.assertEqual(policy.consent(), {'receiveEvents': False, 'shareData': False})

    def test_session_capacity_discards_oldest_and_logout_is_safe(self):
        sessions = OwnerSessions(OWNER)
        cookies = [sessions.login(OWNER) for _ in range(17)]
        self.assertFalse(sessions.has_session(cookies[0]))
        self.assertTrue(sessions.has_session(cookies[-1]))
        sessions.logout(None)
        sessions.logout(cookies[-1])
        self.assertFalse(sessions.has_session(cookies[-1]))

    def test_owner_session_expiration_and_separate_capability(self):
        now = [100.0]
        sessions = OwnerSessions(OWNER, clock=lambda: now[0])
        self.assertTrue(sessions.is_owner_token(OWNER))
        self.assertFalse(sessions.is_owner_token(BRIDGE))
        with self.assertRaises(AuthenticationError): sessions.login(BRIDGE)
        cookie = sessions.login(OWNER)
        self.assertTrue(sessions.has_session(cookie))
        now[0] += SESSION_SECONDS
        self.assertFalse(sessions.has_session(cookie))


class LocalBindAndCredentialsTests(unittest.TestCase):
    def test_refuses_non_loopback_and_invalid_or_equal_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            for host in ('0.0.0.0', '192.168.1.2', '::', '::1', 'example.org'):
                with self.subTest(host=host), self.assertRaises(ValueError):
                    create_server(host, 0, Path(directory)/'not-created', owner_token=OWNER, bridge_token=BRIDGE)
            self.assertFalse((Path(directory)/'not-created').exists())
            with self.assertRaises(ValueError): create_server('127.0.0.1', 0, directory, owner_token=OWNER, bridge_token=OWNER)
            with self.assertRaises(ValueError): create_server('127.0.0.1', 0, directory, owner_token='weak', bridge_token=BRIDGE)
            with self.assertRaises(ValueError): create_server('127.0.0.1', 0, directory)

    def test_cli_refuses_public_bind_without_creating_runtime_data(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / 'should-not-exist'
            result = subprocess.run([sys.executable, 'app.py', '--host', '0.0.0.0', '--port', '0',
                                     '--data-dir', str(data)], cwd=ROOT, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('só permite bind em 127.0.0.1/localhost', result.stderr)
            self.assertFalse(data.exists())

    @unittest.skipUnless(os.name == 'posix', 'permissões POSIX e SIGINT exigidos')
    def test_cli_private_ephemeral_keys_and_clean_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.Popen([sys.executable, 'app.py', '--port', '0', '--data-dir', directory],
                                       cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
            lines = queue.Queue()
            def collect():
                for line in process.stdout:
                    lines.put(line)
            reader = threading.Thread(target=collect, daemon=True)
            reader.start()
            try:
                seen = [lines.get(timeout=10) for _ in range(4)]
                self.assertIn('http://127.0.0.1:', seen[0])
                owner_path = Path(seen[1].split(': ',1)[1].strip())
                bridge_path = Path(seen[2].split(': ',1)[1].strip())
                self.assertEqual(stat.S_IMODE(owner_path.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(bridge_path.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(owner_path.parent.stat().st_mode), 0o700)
                owner = owner_path.read_text().strip()
                bridge = bridge_path.read_text().strip()
                self.assertRegex(owner, r'^[A-Za-z0-9_-]{43}$')
                self.assertRegex(bridge, r'^[A-Za-z0-9_-]{43}$')
                self.assertNotEqual(owner, bridge)
                self.assertNotIn(owner, ''.join(seen))
                self.assertNotIn(bridge, ''.join(seen))
                process.send_signal(signal.SIGINT)
                self.assertEqual(process.wait(timeout=10), 0)
                self.assertFalse(owner_path.exists())
                self.assertFalse(bridge_path.exists())
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                reader.join(timeout=2)
                process.stdout.close()
                process.stderr.close()

    @unittest.skipUnless(os.name == 'posix', 'permissões POSIX exigidas')
    def test_insecure_existing_data_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o755)
            try:
                with self.assertRaises(ValueError):
                    create_server('127.0.0.1', 0, directory, owner_token=OWNER, bridge_token=BRIDGE)
            finally:
                os.chmod(directory, 0o700)


if __name__ == '__main__':
    unittest.main()
