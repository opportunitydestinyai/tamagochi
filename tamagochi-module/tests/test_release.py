from __future__ import annotations
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from tools.make_release import build_release


class ReleaseTests(unittest.TestCase):
    def test_manifest_checksum_and_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'README.md').write_text('demo',encoding='utf-8')
            module=root/'tamagochi-module'; (module/'data').mkdir(parents=True)
            (module/'data'/'private.sqlite3').write_text('private',encoding='utf-8')
            (module/'custom' / '.access').mkdir(parents=True)
            (module/'custom' / '.access' / 'owner.token').write_text('secret',encoding='utf-8')
            (module/'custom' / 'bridge.token').write_text('secret',encoding='utf-8')
            (module/'another-runtime' / 'media').mkdir(parents=True)
            (module/'another-runtime' / 'pet.sqlite3').write_text('private db',encoding='utf-8')
            (module/'another-runtime' / 'media' / 'private.bin').write_text('private media',encoding='utf-8')
            (module/'app.py').write_text('print(1)',encoding='utf-8')
            archive,sidecar=build_release(root)
            self.assertEqual(sidecar.read_text().split()[0],hashlib.sha256(archive.read_bytes()).hexdigest())
            with zipfile.ZipFile(archive) as z:
                self.assertIsNone(z.testzip())
                self.assertIn('tamagochi-module/app.py',z.namelist())
                self.assertIn('tamagochi-module/docs/MANIFESTO.md',z.namelist())
                self.assertIn('tamagochi-module/SHA256SUMS',z.namelist())
                self.assertFalse(any('/data/' in name or '/.access/' in name or name.endswith('.token') or '/another-runtime/' in name for name in z.namelist()))
            for line in (module/'SHA256SUMS').read_text().splitlines():
                sha,name=line.split('  ',1)
                self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),sha)
            first=archive.read_bytes(); build_release(root)
            self.assertEqual(archive.read_bytes(),first,'pacote deve ser determinístico para mesmos arquivos')

if __name__=='__main__': unittest.main()
