#!/usr/bin/env python3
"""Reproducible local HTTP scenario with isolated test-only credentials and data.

Run from the module root: PYTHONPATH=. python3 tests/bridge_scenario.py
No real token or user data is read or printed. The process exits nonzero on mismatch.
"""
from __future__ import annotations

import http.client
import json
import tempfile
import threading

from app import create_server

# Fixed dummy values are only for this disposable local test server.
OWNER = 'O' * 43
BRIDGE = 'B' * 43
EVENT = {
    'eventId': 'scenario-1', 'eventType': 'AGENT_TASK_COMPLETED',
    'timestamp': '2026-10-28T15:00:00-03:00', 'source': 'fixture',
    'payload': {'taskId': 'scenario-task', 'success': True},
}


def main():
    with tempfile.TemporaryDirectory() as directory:
        server = create_server('127.0.0.1', 0, directory, owner_token=OWNER, bridge_token=BRIDGE)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
        thread.start()
        def request(method, path, token=None, body=None, headers=None):
            headers = dict(headers or {})
            if token is not None: headers['Authorization'] = 'Bearer ' + token
            if body is not None:
                headers['Content-Type'] = 'application/json'
                body = json.dumps(body).encode('utf-8')
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            try:
                connection.request(method, path, body, headers)
                response = connection.getresponse()
                payload = response.read()
                return response.status, json.loads(payload) if payload else None
            finally:
                connection.close()
        def check(label, expected, method, path, token=None, body=None, headers=None):
            status, payload = request(method, path, token, body, headers)
            print(f'{label}: HTTP {status}')
            if status != expected:
                raise AssertionError(f'{label}: esperado HTTP {expected}, recebido {status}')
            return payload
        try:
            check('Estado sem credencial', 401, 'GET', '/api/state')
            check('Estado com token da ponte', 401, 'GET', '/api/state', BRIDGE)
            check('Estado com token do proprietário', 200, 'GET', '/api/state', OWNER)
            check('Evento com token da ponte, sem consentimento', 403, 'POST', '/api/bridge/events', BRIDGE, EVENT)
            check('Consentimento tentando usar token da ponte', 401, 'POST', '/api/bridge/consent', BRIDGE,
                  {'receiveEvents':True, 'shareData':True})
            check('Proprietário autoriza só entrada', 200, 'POST', '/api/bridge/consent', OWNER,
                  {'receiveEvents':True, 'shareData':False})
            ack = check('Evento autorizado', 200, 'POST', '/api/bridge/events', BRIDGE, EVENT)
            if ack != {'duplicate': False, 'duplicateKind': None, 'xpAwarded': 15}:
                raise AssertionError('A resposta de entrada não corresponde ao ACK mínimo esperado.')
            print('Resposta mínima:', json.dumps(ack, ensure_ascii=False, sort_keys=True))
            check('Contexto sem consentimento de saída', 403, 'GET', '/api/bridge/context', BRIDGE)
            check('Proprietário revoga entrada e autoriza saída', 200, 'POST', '/api/bridge/consent', OWNER,
                  {'receiveEvents':False, 'shareData':True})
            check('Evento após revogação de entrada', 403, 'POST', '/api/bridge/events', BRIDGE, EVENT)
            check('Contexto com consentimento de saída', 200, 'GET', '/api/bridge/context', BRIDGE)
            check('Proprietário revoga todos os escopos', 200, 'POST', '/api/bridge/consent', OWNER,
                  {'receiveEvents':False, 'shareData':False})
            check('Contexto após revogação', 403, 'GET', '/api/bridge/context', BRIDGE)
            check('Origem hostil com X-Forwarded-Host forjado', 403, 'GET', '/api/state', OWNER,
                  headers={'Origin':'https://evil.example', 'X-Forwarded-Host':'evil.example'})
            print('OK — cenário isolado, sem credenciais ou dados reais.')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    main()
