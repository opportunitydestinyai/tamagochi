"""Controlled, byte-preserving import of approved SL-001 videos and posters."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path

from .model import PetError

STATES = ("idle", "happy", "thinking", "resting", "milestone")
SLOTS = {f"{state}_{kind}" for state in STATES for kind in ("video", "poster")}
MAX_BYTES = 50 * 1024 * 1024


def detect(data):
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video/mp4"
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise PetError("Formato não reconhecido; use MP4/WebM ou JPG/PNG/WebP.")


class MediaStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    @staticmethod
    def _slot(slot):
        if slot not in SLOTS:
            raise PetError("Posição de mídia desconhecida.")
        return slot

    def _metadata(self, slot):
        file = self.path / f"{self._slot(slot)}.json"
        if not file.exists():
            return None
        meta = json.loads(file.read_text(encoding="utf-8"))
        sha = meta.get("sha256", "")
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise RuntimeError("Manifesto de mídia corrompido.")
        if not (self.path / f"{sha}.bin").is_file():
            raise RuntimeError("Arquivo original da mídia está ausente.")
        return meta

    def all(self):
        with self.lock:
            return {slot: meta for slot in sorted(SLOTS) if (meta := self._metadata(slot)) is not None}

    def get(self, slot):
        with self.lock:
            meta = self._metadata(slot)
            return (self.path / f"{meta['sha256']}.bin", meta) if meta else None

    def _atomic(self, path, data):
        fd, name = tempfile.mkstemp(prefix=".upload-", dir=self.path)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def put(self, slot, data):
        slot = self._slot(slot)
        if not data or len(data) > MAX_BYTES:
            raise PetError("Mídia vazia ou maior que 50 MiB.")
        mime = detect(data)
        if slot.endswith("_video") != mime.startswith("video/"):
            raise PetError("O tipo do arquivo não corresponde à posição escolhida.")
        sha = hashlib.sha256(data).hexdigest()
        meta = {"sha256": sha, "size": len(data), "mime": mime}
        with self.lock:
            old = self._metadata(slot)
            asset = self.path / f"{sha}.bin"
            if not asset.exists():
                self._atomic(asset, data)
            self._atomic(self.path / f"{slot}.json", json.dumps(meta, sort_keys=True).encode("utf-8"))
            if old and old["sha256"] != sha:
                self._remove_unreferenced(old["sha256"])
        return meta

    def _remove_unreferenced(self, sha):
        for slot in SLOTS:
            meta_file = self.path / f"{slot}.json"
            if meta_file.exists() and json.loads(meta_file.read_text(encoding="utf-8")).get("sha256") == sha:
                return
        (self.path / f"{sha}.bin").unlink(missing_ok=True)

    def delete(self, slot):
        slot = self._slot(slot)
        with self.lock:
            meta = self._metadata(slot)
            if meta is None:
                return False
            (self.path / f"{slot}.json").unlink()
            self._remove_unreferenced(meta["sha256"])
            return True
