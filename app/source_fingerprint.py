"""Non-secret fingerprint for verifying deployed source matches public evaluation."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def pipeline_sha256() -> str:
    files=sorted((ROOT/'app').glob('*.py'))
    files += [ROOT/'data'/'semantic_model.md',ROOT/'data'/'schema.sql',ROOT/'data'/'football.db']
    files += sorted((ROOT/'static').glob('*'))
    digest=sha256()
    for path in files:
        rel=path.relative_to(ROOT).as_posix().encode('utf-8')
        digest.update(len(rel).to_bytes(4,'big'));digest.update(rel)
        contents=path.read_bytes()
        digest.update(len(contents).to_bytes(8,'big'));digest.update(contents)
    return digest.hexdigest()
