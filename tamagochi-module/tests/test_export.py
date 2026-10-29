from __future__ import annotations
import hashlib
import tempfile
import unittest
from pathlib import Path
from pet.repository import PetRepository
from pet.service import PetEngine
from pet.media import MediaStore
from tools.export_private_data import export


class ExportTests(unittest.TestCase):
    def test_consistent_private_export_includes_wal_and_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)/'data'; repo=PetRepository(data/'pet.sqlite3'); engine=PetEngine(repo)
            engine.perform_action('LEARN','private-export-test')
            blob=b'\x00\x00\x00\x18ftypisom'+b'fixture'
            MediaStore(data/'media').put('idle_video',blob)
            (data/'.access').mkdir()
            (data/'.access'/'owner.token').write_text('private token',encoding='utf-8')
            out=Path(tmp)/'snapshot'; export(data,out)
            self.assertFalse((out/'.access').exists())
            self.assertFalse(any(p.name.endswith('.token') for p in out.rglob('*')))
            for line in (out/'SHA256SUMS').read_text().splitlines():
                digest,name=line.split('  ',1)
                self.assertEqual(hashlib.sha256((out/name).read_bytes()).hexdigest(),digest)
            restored=PetEngine(PetRepository(out/'pet.sqlite3'))
            self.assertEqual(restored.snapshot(run_due=False)['xp'],13)
            self.assertEqual(MediaStore(out/'media').get('idle_video')[0].read_bytes(),blob)
            with self.assertRaises(FileExistsError): export(data,out)
            with self.assertRaises(ValueError): export(data,data/'nested')

if __name__=='__main__': unittest.main()
