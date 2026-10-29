#!/usr/bin/env python3
"""Generate a manifest, checksums and a portable source ZIP without private data."""
from __future__ import annotations

import hashlib
import os
import zipfile
from pathlib import Path

ARCHIVE_NAME = 'Modulo_Tamagotchi_Evolutivo_T1.zip'
EXCLUDED_DIRS = {'.git', 'data', '.access', 'node_modules', '__pycache__', '.venv', 'releases', '.cache', '.pytest_cache'}
FIXED_DATE = (2026, 10, 28, 0, 0, 0)


def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def build_release(root: Path) -> tuple[Path, Path]:
    root=root.resolve(); module=root/'tamagochi-module'
    if not (root/'README.md').is_file() or not module.is_dir():
        raise ValueError('A raiz deve conter README.md e tamagochi-module/.')
    manifest=module/'docs'/'MANIFESTO.md'; checksums=module/'SHA256SUMS'
    manifest.parent.mkdir(parents=True,exist_ok=True)
    files=[p for p in (root/'README.md',root/'.gitignore') if p.is_file()]
    for base, dirs, names in os.walk(module):
        # A custom data directory may be named something other than "data".
        # Never package any part of a directory containing a live pet database.
        if 'pet.sqlite3' in names:
            if Path(base) == module:
                raise ValueError('O banco de execução não pode ficar na raiz do módulo.')
            dirs[:] = []
            continue
        dirs[:]=sorted(d for d in dirs if d not in EXCLUDED_DIRS)
        for name in sorted(names):
            file=Path(base)/name
            if file in {manifest, checksums} or file.is_symlink() or name.endswith(('.pyc','.token','.sqlite3','.sqlite3-wal','.sqlite3-shm')):
                continue
            files.append(file)
    files=sorted(files,key=lambda p:p.relative_to(root).as_posix())
    listing='\n'.join(f'- `{p.relative_to(root).as_posix()}` ({p.stat().st_size} bytes)' for p in files)
    manifest.write_text('# Manifesto de entrega\n\nGerado por `tools/make_release.py`. O pacote inclui os arquivos abaixo, este manifesto e `tamagochi-module/SHA256SUMS`. Banco de execução, mídias privadas importadas, dependências instaladas, Git e credenciais não são incluídos. Os vídeos/posters SL-001 aprovados não foram fornecidos.\n\n'+listing+'\n',encoding='utf-8')
    all_files=sorted([*files,manifest],key=lambda p:p.relative_to(root).as_posix())
    checksums.write_text(''.join(f'{digest(p)}  {p.relative_to(root).as_posix()}\n' for p in all_files),encoding='utf-8')
    archive=root/ARCHIVE_NAME
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as output:
        for file in sorted([*all_files,checksums],key=lambda p:p.relative_to(root).as_posix()):
            info=zipfile.ZipInfo(file.relative_to(root).as_posix(),date_time=FIXED_DATE)
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o644 << 16
            output.writestr(info,file.read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    sidecar=root/(ARCHIVE_NAME+'.sha256')
    sidecar.write_text(f'{digest(archive)}  {archive.name}\n',encoding='utf-8')
    with zipfile.ZipFile(archive) as output:
        if output.testzip() is not None:
            raise RuntimeError('A verificação interna do ZIP falhou.')
    return archive,sidecar


def main():
    root=Path(__file__).resolve().parents[2]
    archive,sidecar=build_release(root)
    print(f'ZIP: {archive}\nSHA-256: {sidecar}\nManifesto: {root / "tamagochi-module/docs/MANIFESTO.md"}')


if __name__=='__main__': main()
