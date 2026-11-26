"""One-time, idempotent migration of obsolete top-k/template regression tests.

No production app source is deleted. This relocates historical tests that
assert removed evaluation-shaped behavior into the committed audit archive.
"""
from __future__ import annotations
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OLD=('test_contract_v4.py','test_goalkeeper_v43.py','test_semantics_v42.py',
     'test_v41.py','test_quality_v3.py')

def main():
    archive=ROOT/'docs'/'legacy_tests'
    archive.mkdir(parents=True,exist_ok=True)
    for filename in OLD:
        src=ROOT/'tests'/filename
        if not src.exists():
            print('Already archived:',filename)
            continue
        dst=archive/filename
        if dst.exists() and dst.read_bytes()==src.read_bytes():
            src.unlink()
            print('Same historical test already preserved:',filename)
            continue
        if dst.exists():
            backup=archive/(filename+'.local_original')
            n=1
            while backup.exists():
                backup=archive/(filename+f'.local_original_{n}')
                n+=1
            src.rename(backup)
            print('Archived locally altered legacy test at:',backup)
        else:
            src.rename(dst)
            print('Archived:',dst)
    print('Migration complete. Run: python3 scripts/preflight.py')

if __name__=='__main__':main()
