#!/usr/bin/env python3
"""Create an explicit, consistent private-data export; never includes credentials.

Stop the server first to keep SQLite and media in the same point-in-time snapshot.
The output may contain private user-supplied media and must not be committed.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import shutil
import sqlite3
from pathlib import Path


def export(data_dir: Path, output: Path) -> None:
    source = data_dir.resolve()
    destination = output.resolve()
    if source == destination or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("O destino deve ser separado do diretório de dados.")
    db = source / 'pet.sqlite3'
    if not db.is_file():
        raise FileNotFoundError("Banco pet.sqlite3 não encontrado.")
    destination.mkdir(parents=True, exist_ok=False)
    try:
        # SQLite backup captures committed data, including committed WAL content.
        with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as original:
            with closing(sqlite3.connect(destination / 'pet.sqlite3')) as target:
                original.backup(target)
                if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('A integridade do snapshot SQLite falhou.')
        media = source / 'media'
        if media.is_dir():
            (destination / 'media').mkdir()
            for item in sorted(media.iterdir()):
                # Only the controlled media store, not unrelated files or symlinks.
                if item.is_file() and not item.is_symlink() and item.suffix in {'.json', '.bin'}:
                    shutil.copyfile(item, destination / 'media' / item.name)
        lines=[]
        for item in sorted(destination.rglob('*')):
            if item.is_file():
                lines.append(f"{hashlib.sha256(item.read_bytes()).hexdigest()}  {item.relative_to(destination).as_posix()}")
        (destination / 'SHA256SUMS').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    except BaseException:
        shutil.rmtree(destination,ignore_errors=True)
        raise


def main():
    parser=argparse.ArgumentParser(description='Exporta SQLite e mídias privadas; pare o servidor antes.')
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True,help='Diretório novo e privado, fora do repositório')
    parser.add_argument('--server-stopped',action='store_true',help='Confirma que o servidor foi parado para consistência com as mídias')
    args=parser.parse_args()
    if not args.server_stopped:
        parser.error('Pare o servidor e confirme com --server-stopped.')
    export(args.data_dir,args.output)
    print(f'Snapshot privado criado em {args.output}; verifique SHA256SUMS antes do upload.')


if __name__=='__main__': main()
