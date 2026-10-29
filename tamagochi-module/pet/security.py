"""In-memory local access primitives; no credentials are persisted in SQLite.

This is a single-user prototype boundary, not a replacement for a production
identity provider, TLS, multi-user authorization, or OS-level isolation.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import threading
import time

# secrets.token_urlsafe(32) yields 43 base64url characters / 256 random bits.
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
SESSION_SECONDS = 8 * 60 * 60
MAX_SESSIONS = 16


class AuthenticationError(Exception):
    """The caller did not supply the credential for the requested role."""


def new_token() -> str:
    return secrets.token_urlsafe(32)


def candidate_digest(token):
    if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
        return None
    return hashlib.sha256(token.encode("ascii")).digest()


def token_digest(token):
    result = candidate_digest(token)
    if result is None:
        raise ValueError("A credencial deve ter o formato de token aleatório de 32 bytes.")
    return result


class OwnerSessions:
    """Separate owner bearer capability and short-lived HttpOnly browser sessions."""
    def __init__(self, owner_token, *, clock=time.monotonic):
        self._owner_digest = token_digest(owner_token)
        self._sessions = {}
        self._lock = threading.Lock()
        self._clock = clock

    def is_owner_token(self, token):
        digest = candidate_digest(token)
        return digest is not None and secrets.compare_digest(digest, self._owner_digest)

    def login(self, token):
        if not self.is_owner_token(token):
            raise AuthenticationError("Credencial inválida.")
        session = new_token()
        with self._lock:
            self._prune()
            if len(self._sessions) >= MAX_SESSIONS:
                del self._sessions[min(self._sessions, key=self._sessions.get)]
            self._sessions[token_digest(session)] = self._clock() + SESSION_SECONDS
        return session

    def _prune(self):
        now = self._clock()
        for digest, expires in list(self._sessions.items()):
            if expires <= now:
                del self._sessions[digest]

    def has_session(self, session):
        digest = candidate_digest(session)
        if digest is None:
            return False
        with self._lock:
            self._prune()
            return digest in self._sessions

    def logout(self, session):
        digest = candidate_digest(session)
        if digest is not None:
            with self._lock:
                self._sessions.pop(digest, None)
