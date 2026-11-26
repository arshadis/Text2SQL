"""Non-secret fingerprint for verifying deployed source matches public evaluation."""
from __future__ import annotations
from hashlib import sha256
import json
import os
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


# Runtime settings change model behavior without changing Python source.
# Publish ONLY a one-way digest of ordinary non-secret configuration; never
# include GAPGPT_API_KEY or any authentication token in this fingerprint.
def runtime_config_sha256() -> str:
    defaults={
        'GAPGPT_MODEL':'gpt-4o-mini',
        'GAPGPT_TIMEOUT_SECONDS':'12',
        'GAPGPT_REVIEW_ENABLED':'1',
        'GAPGPT_STRICT_REVIEW':'1',
        'RESULT_NORMALIZATION_ENABLED':'1',
    }
    settings={key:os.getenv(key,value) for key,value in defaults.items()}
    payload=json.dumps(settings,sort_keys=True,ensure_ascii=True,separators=(',',':'))
    return sha256(payload.encode('utf-8')).hexdigest()
