"""Verify live GapGPT routing using non-secret deployment metadata and local HTTP reports.

This runs on a laptop. It only GETs the public service URL and reads local
report files; it never needs, reads or prints the provider API key.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from urllib.request import urlopen

OFFICIAL='https://api.gapgpt.app/v1'


def verify(meta: dict, report: dict, label: str) -> list[str]:
    errors=[]
    for key in ('pipeline_sha256','runtime_config_sha256','provider_model','provider_base_url'):
        if report.get(key)!=meta.get(key):
            errors.append(f'{label}: mismatch {key}: report={report.get(key)!r}, deployment={meta.get(key)!r}')
    return errors


def main(argv=None):
    parser=argparse.ArgumentParser(description='Verify GapGPT provider identity without exposing API keys')
    parser.add_argument('public_url',help='https://your-app.darkube.ir')
    parser.add_argument('--reports',default='reports',help='Local reports directory')
    args=parser.parse_args(argv)
    base=args.public_url.rstrip('/')
    if not base.startswith('https://'): parser.error('A public HTTPS URL is required')
    with urlopen(base+'/api/meta',timeout=15) as response:
        meta=json.load(response)
    print('Deployment URL:',base)
    print('Configured provider:',meta.get('provider_base_url'))
    print('Requested model:',meta.get('provider_model'))
    print('Pipeline fingerprint:',meta.get('pipeline_sha256'))
    print('Config fingerprint:',meta.get('runtime_config_sha256'))
    errors=[]
    if meta.get('provider_base_url')!=OFFICIAL:
        errors.append('Deployment does not attest to the official GapGPT API endpoint')
    if not meta.get('pipeline_sha256') or not meta.get('runtime_config_sha256'):
        errors.append('Missing release provenance')
    root=Path(args.reports)
    for name in ('eval_report.json','generalization_probe.json','traces.json'):
        path=root/name
        if not path.is_file():
            errors.append(f'Missing local report {path}')
            continue
        d=json.loads(path.read_text(encoding='utf-8'))
        if (d.get('url') or d.get('public_url','')).rstrip('/')!=base:
            errors.append(f'{name}: report URL differs from deployment URL')
        errors.extend(verify(meta,d,name))
        observations=[]
        if 'probes' in d:
            observations=[x.get('response') for x in d['probes']]
        if 'traces' in d:
            observations=[x.get('response') for x in d['traces']]
        for obs in observations:
            if not isinstance(obs,dict):continue
            diag=obs.get('model_diagnostics')
            if not diag:continue   # Policy refusals bypass model, as intended
            if diag.get('provider')!='GapGPT' or diag.get('provider_base_url')!=OFFICIAL:
                errors.append(f'{name}: a model diagnostic does not attest to official GapGPT')
        print(f'{name}: checked')
    if errors:
        print('AUDIT FAILED:')
        for msg in errors:print(' -',msg)
        return 1
    print('AUDIT PASSED: remote endpoint, model, fingerprints and local reports are consistent.')
    print('This proves application routing/configuration, not independent ownership of an upstream response.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
