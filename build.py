#!/usr/bin/env python3
"""Convert all manifest assets, verify RML, and build using the official CLI."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from convert_flare import read_flare, to_rml

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rive', default='rive', help='Rive CLI executable (tested: 1.0.2)')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'assets.json').read_text())
    demo_manifest = []
    for asset in manifest:
        source = ROOT / 'sources' / asset['source']
        project = ROOT / 'projects' / asset['project']
        data = source.read_bytes()
        document = read_flare(data)
        (project / 'scene.rml').write_text(to_rml(document))
        report = {'source': source.name, 'sha256': hashlib.sha256(data).hexdigest(), **document}
        (project / 'source.json').write_text(json.dumps(report, indent=2) + '\n')
        subprocess.run([args.rive, str(project), '--verify'], check=True)
        inspected = subprocess.run([args.rive, 'inspect', str(project)], check=True, capture_output=True, text=True)
        if json.loads(inspected.stdout)['problems']:
            raise RuntimeError(inspected.stdout)
        subprocess.run([args.rive, str(project), '--once'], check=True)
        (project / 'build/inspect.json').write_text(inspected.stdout)
        for folder in ('demo/assets', 'validation/flare_compare/assets'):
            (ROOT / folder).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project / f'build/{asset["project"]}.riv', ROOT / folder / asset['output'])
        shutil.copyfile(source, ROOT / 'validation/flare_compare/assets' / source.name)
        board = document['artboards'][0]
        demo_manifest.append({**asset, 'animations': [
            {'name': a['name'], 'fps': a['fps'], 'duration': a['duration'], 'loop': a['loop'],
             'keyFrames': sorted({round(k['time']*a['fps']) for t in a['tracks'] for k in t['keys']})}
            for a in board['animations']]})
        print(f'Ready: {asset["output"]} ({len(board["animations"])} animations)')
    for folder in ('demo/assets', 'validation/flare_compare/assets'):
        (ROOT / folder / 'manifest.json').write_text(json.dumps(demo_manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
