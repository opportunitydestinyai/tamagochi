#!/usr/bin/env python3
"""Offline-first, single-user prototype HTTP server (Python standard library)."""
from __future__ import annotations

import argparse
import ipaddress
import json
import logging
import mimetypes
import os
import re
import secrets
import sqlite3
import tempfile
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from pet.bridge import BridgePolicy, MusePetBridge
from pet.media import MAX_BYTES, MediaStore
from pet.model import ConflictError, PetError, validate_config
from pet.repository import PetRepository
from pet.security import AuthenticationError, OwnerSessions, SESSION_SECONDS, new_token, token_digest
from pet.service import PetEngine

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
logger = logging.getLogger("pet.http")


def create_server(host="127.0.0.1", port=8765, data_dir=None, initial_config=None, *, owner_token=None, bridge_token=None):
    # No wildcard, public, LAN, or reverse-proxy bind in this prototype.
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("Este protótipo só permite bind em 127.0.0.1/localhost; não exponha na rede.")
    if secrets.compare_digest(token_digest(owner_token), token_digest(bridge_token)):
        raise ValueError("As credenciais do proprietário e da ponte devem ser distintas.")
    data_dir = Path(data_dir or os.environ.get("PET_DATA_DIR", ROOT / "data")).resolve()
    data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix" and data_dir.stat().st_mode & 0o077:
        raise ValueError("O diretório de dados deve ser privado (chmod 700) antes de iniciar.")
    repo = PetRepository(data_dir / "pet.sqlite3", initial_config=initial_config)
    engine = PetEngine(repo)
    media = MediaStore(data_dir / "media")
    owner_sessions = OwnerSessions(owner_token)
    bridge_policy = BridgePolicy(bridge_token)
    bridge = MusePetBridge(engine, bridge_policy)

    class Handler(BaseHTTPRequestHandler):
        server_version = "MusePet/0.1"
        sys_version = ""

        def log_message(self, fmt, *args):
            # Do not log query strings, authorization headers, cookies or bodies.
            status = str(args[1]) if len(args) > 1 else "-"
            logger.info(json.dumps({"method": self.command, "path": urlsplit(self.path).path,
                                    "status": status}, ensure_ascii=False))

        def _headers(self, status, content_type, size, *, cache="no-store", extra=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; media-src 'self' blob:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
            # Intentionally no Access-Control-Allow-Origin/credentials headers.
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()

        def _json(self, status, obj, *, extra=None):
            data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self._headers(status, "application/json; charset=utf-8", len(data), extra=extra)
            if self.command != "HEAD":
                self.wfile.write(data)

        def _error(self, status, message):
            extra = {"WWW-Authenticate": 'Bearer realm="MusePet"'} if status == 401 else None
            self._json(status, {"error": message}, extra=extra)

        def _validate_request_origin(self):
            # Ignore untrusted X-Forwarded-*; reverse proxies are not supported.
            if not ipaddress.ip_address(self.client_address[0]).is_loopback:
                raise PermissionError("Somente clientes locais são permitidos.")
            hosts = self.headers.get_all("Host", [])
            if len(hosts) != 1:
                raise PermissionError("Host local obrigatório.")
            try:
                host = urlsplit("http://" + hosts[0])
                if (host.hostname not in {"127.0.0.1", "localhost"} or
                    (host.port or 80) != self.server.server_port or host.username is not None or
                    host.password is not None or host.path or host.query or host.fragment):
                    raise ValueError("host")
                origins = self.headers.get_all("Origin", [])
                if len(origins) > 1:
                    raise ValueError("origin")
                if origins:
                    origin = urlsplit(origins[0])
                    if (origin.scheme != "http" or origin.hostname != host.hostname or
                        (origin.port or 80) != (host.port or 80) or origin.username is not None or
                        origin.password is not None or origin.path or origin.query or origin.fragment):
                        raise ValueError("origin")
            except ValueError as exc:
                raise PermissionError("Host ou origem não corresponde ao aplicativo local.") from exc

        def _bearer(self):
            values = self.headers.get_all("Authorization", [])
            if len(values) != 1:
                return None
            match = re.fullmatch(r"(?i:Bearer) ([A-Za-z0-9_-]{43})", values[0])
            return match.group(1) if match else None

        def _session(self):
            values = self.headers.get_all("Cookie", [])
            if len(values) != 1:
                return None
            try:
                cookie = SimpleCookie()
                cookie.load(values[0])
                return cookie["muse_owner"].value if "muse_owner" in cookie else None
            except CookieError:
                return None

        def _marker(self):
            return self.headers.get_all("X-Pet-Request", []) == ["1"]

        def _require_owner(self, path):
            # An invalid Authorization header never falls back to a cookie.
            if self.headers.get_all("Authorization", []):
                if not owner_sessions.is_owner_token(self._bearer()):
                    raise AuthenticationError("Credencial inválida.")
                return
            if not owner_sessions.has_session(self._session()):
                raise AuthenticationError("Autenticação local necessária.")
            if path.startswith("/api/") and not self._marker():
                raise PermissionError("Cabeçalho de proteção da sessão ausente.")
            if self.command not in {"GET", "HEAD"} and not self.headers.get("Origin"):
                raise PermissionError("Origem obrigatória para alterar dados na sessão do navegador.")

        def _body(self, max_size, *, json_body=False):
            if self.headers.get("Transfer-Encoding"):
                raise PetError("Transfer-Encoding não é suportado.")
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError as exc:
                raise PetError("Content-Length inválido.") from exc
            if length < 0 or length > max_size:
                raise PetError("O conteúdo está vazio ou ultrapassa o limite permitido.")
            if json_body and self.headers.get_content_type() != "application/json":
                raise PetError("Use Content-Type application/json.")
            data = self.rfile.read(length)
            if len(data) != length:
                raise PetError("Envio incompleto.")
            if not json_body:
                return data
            try:
                return json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeError) as exc:
                raise PetError("JSON inválido.") from exc

        def _file(self, path, content_type, *, range_allowed=False):
            size = path.stat().st_size
            start, end = 0, size - 1
            status = HTTPStatus.OK
            extra = {}
            if range_allowed:
                extra["Accept-Ranges"] = "bytes"
                value = self.headers.get("Range")
                if value:
                    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
                    if not match or not (match.group(1) or match.group(2)):
                        self._headers(416, content_type, 0, extra={"Content-Range": f"bytes */{size}"})
                        return
                    if match.group(1):
                        start = int(match.group(1))
                        end = min(int(match.group(2)) if match.group(2) else size - 1, size - 1)
                    else:
                        length = int(match.group(2))
                        start = max(0, size - length)
                    if start >= size or start > end:
                        self._headers(416, content_type, 0, extra={"Content-Range": f"bytes */{size}"})
                        return
                    status = HTTPStatus.PARTIAL_CONTENT
                    extra["Content-Range"] = f"bytes {start}-{end}/{size}"
            self._headers(status, content_type, end - start + 1, extra=extra)
            if self.command == "HEAD":
                return
            with path.open("rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = f.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def _route(self):
            self._validate_request_origin()
            url = urlsplit(self.path)
            path = unquote(url.path)
            q = parse_qs(url.query)
            method = self.command

            if path == "/api/session":
                if method in {"GET", "HEAD"}:
                    if self.headers.get_all("Authorization", []):
                        authenticated = owner_sessions.is_owner_token(self._bearer())
                    else:
                        authenticated = self._marker() and owner_sessions.has_session(self._session())
                    return self._json(200, {"authenticated": bool(authenticated)})
                if method == "POST":
                    if not self.headers.get("Origin") or not self._marker():
                        raise PermissionError("Origem local e cabeçalho de sessão são obrigatórios.")
                    data = self._body(1024, json_body=True)
                    if not isinstance(data, dict) or set(data) != {"token"}:
                        raise PetError("Informe somente a credencial local.")
                    session = owner_sessions.login(data["token"])
                    cookie = f"muse_owner={session}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_SECONDS}"
                    return self._json(200, {"authenticated": True}, extra={"Set-Cookie": cookie})
                if method == "DELETE":
                    self._require_owner(path)
                    owner_sessions.logout(self._session())
                    bridge_policy.set_consent({"receiveEvents": False, "shareData": False})
                    return self._json(200, {"authenticated": False}, extra={"Set-Cookie": "muse_owner=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"})
                return self._error(405, "Método não permitido.")

            bridge_path = path in {"/api/bridge/events", "/api/bridge/context", "/api/events"}
            if bridge_path:
                # Check before parsing a body, then the adapter rechecks atomically
                # before processing. Revocation never waits for a slow upload body.
                credential = self._bearer()
                bridge_policy.check_token(credential)
                scope = ("receiveEvents" if path == "/api/bridge/events" and method == "POST" else
                         "shareData" if path in {"/api/bridge/context", "/api/events"} and method in {"GET", "HEAD"} else None)
                if scope:
                    with bridge_policy.authorized(credential, scope):
                        pass
            elif path.startswith("/api/") or path.startswith("/media/"):
                self._require_owner(path)

            if method in {"GET", "HEAD"}:
                if path == "/api/state":
                    return self._json(200, {"state": engine.snapshot()})
                if path == "/api/config":
                    return self._json(200, {"config": engine.get_config()})
                if path == "/api/memories":
                    limit, offset = max(1, min(int(q.get("limit", ["100"])[0]), 500)), max(0, int(q.get("offset", ["0"])[0]))
                    memories, total = engine.memories_page(limit=limit, offset=offset)
                    return self._json(200, {"memories": memories, "total": total, "hasMore": offset + len(memories) < total})
                if path == "/api/bridge/consent":
                    return self._json(200, {"consent": bridge_policy.consent()})
                if path == "/api/bridge/context":
                    return self._json(200, {"context": bridge.context(credential=self._bearer())})
                if path == "/api/events":
                    return self._json(200, {"events": bridge.outgoing(after=int(q.get("after", ["0"])[0]), limit=int(q.get("limit", ["100"])[0]), credential=self._bearer())})
                if path == "/api/ui/events":
                    # Local owner UI needs milestones even while the bridge is off.
                    return self._json(200, {"events": engine.events(after=int(q.get("after", ["0"])[0]), limit=int(q.get("limit", ["100"])[0]))})
                if path == "/api/ui/events/cursor":
                    # Owner-only boundary for starting a new UI session without
                    # replaying an arbitrarily long historical event stream.
                    return self._json(200, {"cursor": engine.event_cursor()})
                if path == "/api/awards":
                    limit, offset = max(1, min(int(q.get("limit", ["20"])[0]), 500)), max(0, int(q.get("offset", ["0"])[0]))
                    items, total = engine.awards_page(limit=limit, offset=offset)
                    return self._json(200, {"awards": items, "total": total, "hasMore": offset + len(items) < total})
                if path == "/api/autonomy/history":
                    limit, offset = max(1, min(int(q.get("limit", ["20"])[0]), 500)), max(0, int(q.get("offset", ["0"])[0]))
                    items = engine.autonomy_history(limit=limit + 1, offset=offset)
                    return self._json(200, {"history": items[:limit], "hasMore": len(items) > limit})
                if path == "/api/media":
                    return self._json(200, {"media": media.all()})
                if path.startswith("/media/"):
                    slot = path.removeprefix("/media/")
                    result = media.get(slot)
                    if not result:
                        return self._error(404, "Mídia ainda não importada.")
                    return self._file(result[0], result[1]["mime"], range_allowed=True)
                if path.startswith("/api/"):
                    return self._error(404, "Rota não encontrada.")
                relative = "index.html" if path == "/" else path.lstrip("/")
                target = (WEB / relative).resolve()
                if not target.is_relative_to(WEB.resolve()) or not target.is_file():
                    return self._error(404, "Arquivo não encontrado.")
                mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                if mime.startswith("text/") or mime in ("application/javascript", "application/json"):
                    mime += "; charset=utf-8"
                return self._file(target, mime)
            if method == "POST":
                if path.startswith("/api/media/"):
                    slot = path.removeprefix("/api/media/")
                    return self._json(201, {"media": media.put(slot, self._body(MAX_BYTES))})
                data = self._body(64 * 1024, json_body=True)
                if not isinstance(data, dict):
                    raise PetError("O corpo deve ser um objeto JSON.")
                if path == "/api/actions":
                    if set(data) - {"action", "eventId", "meaningful"} or "action" not in data or "eventId" not in data:
                        raise PetError("Informe action e eventId.")
                    return self._json(200, engine.perform_action(data["action"], data["eventId"], meaningful=data.get("meaningful", False)))
                if path == "/api/autonomy/run":
                    if set(data) != {"activity", "eventId"}:
                        raise PetError("Informe activity e eventId.")
                    return self._json(200, engine.run_activity(data["activity"], data["eventId"]))
                if path == "/api/bridge/events":
                    return self._json(200, bridge.receive(data, credential=self._bearer()))
                if path == "/api/bridge/consent":
                    return self._json(200, {"consent": bridge_policy.set_consent(data)})
                if path == "/api/customization":
                    return self._json(200, {"state": engine.customize(data)})
                if path == "/api/config":
                    return self._json(200, engine.update_config(data))
                return self._error(404, "Rota não encontrada.")
            if method == "DELETE":
                if path == "/api/memories":
                    return self._json(200, {"deleted": engine.delete_memories()})
                if path.startswith("/api/memories/"):
                    return self._json(200, {"deleted": engine.delete_memories(path.removeprefix("/api/memories/"))})
                if path.startswith("/api/media/"):
                    return self._json(200, {"deleted": media.delete(path.removeprefix("/api/media/"))})
                return self._error(404, "Rota não encontrada.")
            return self._error(405, "Método não permitido.")

        def _handle(self):
            try:
                self._route()
            except AuthenticationError as exc:
                self._error(401, str(exc))
            except PermissionError as exc:
                self._error(403, str(exc))
            except ConflictError as exc:
                self._error(409, str(exc))
            except (PetError, ValueError, TypeError, KeyError) as exc:
                self._error(400, str(exc) or "Requisição inválida.")
            except (BrokenPipeError, ConnectionResetError):
                pass
            except sqlite3.Error:
                logger.exception("storage_failure")
                self._error(503, "Não foi possível acessar o armazenamento; nenhuma alteração parcial foi confirmada.")
            except Exception:
                logger.exception("request_failure")
                self._error(500, "Falha interna; consulte o log local.")

        do_GET = _handle
        do_HEAD = _handle
        do_POST = _handle
        do_DELETE = _handle
        do_OPTIONS = _handle

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.pet_engine = engine
    server.pet_repository = repo
    server.media_store = media
    return server


def _write_token(path, token):
    # The parent is a freshly created private directory; never follow a file link.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as file:
        file.write(token + "\n")


def main():
    parser = argparse.ArgumentParser(description="Muse SL-001: protótipo local independente")
    parser.add_argument("--host", default="127.0.0.1", help="Somente 127.0.0.1 ou localhost (sem acesso pela rede)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", help="Diretório privado para SQLite e mídias fornecidas pelo usuário")
    parser.add_argument("--config", help="Arquivo JSON de regras para criar um banco novo (não sobrescreve banco existente)")
    args = parser.parse_args()
    initial_config = validate_config(json.loads(Path(args.config).read_text(encoding="utf-8"))) if args.config else None
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    owner_token, bridge_token = new_token(), new_token()
    data_dir = Path(args.data_dir or os.environ.get("PET_DATA_DIR", ROOT / "data")).resolve()
    try:
        server = create_server(args.host, args.port, data_dir, initial_config, owner_token=owner_token, bridge_token=bridge_token)
    except ValueError as exc:
        parser.error(str(exc))
    try:
        access_dir = data_dir / ".access"
        if access_dir.is_symlink():
            raise RuntimeError("O diretório .access não pode ser um link simbólico.")
        access_dir.mkdir(mode=0o700, exist_ok=True)
        if os.name == "posix":
            os.chmod(access_dir, 0o700)
        with tempfile.TemporaryDirectory(prefix="session-", dir=access_dir) as directory:
            try:
                owner_path = Path(directory) / "owner.token"
                bridge_path = Path(directory) / "bridge.token"
                _write_token(owner_path, owner_token)
                _write_token(bridge_path, bridge_token)
                print(f"SL-001 disponível em http://127.0.0.1:{server.server_port} (modo local, sem agente)", flush=True)
                print(f"Credencial do proprietário (arquivo privado): {owner_path}", flush=True)
                print(f"Credencial da ponte (arquivo privado): {bridge_path}", flush=True)
                print("Não compartilhe as credenciais. A ponte inicia sem consentimento; acesso de rede é bloqueado.", flush=True)
                server.serve_forever(poll_interval=0.5)
            except KeyboardInterrupt:
                pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
