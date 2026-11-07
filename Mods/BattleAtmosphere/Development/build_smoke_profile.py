"""Official smoke-only build. No install, UI, or running-game modification."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import sys
from apply_smoke_profile import protected_files

DEV = Path(__file__).resolve().parent
MOD = DEV.parent
ROOT = MOD.parents[1]

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    running = subprocess.run(['powershell', '-NoProfile', '-Command',
        'Get-Process WARNO -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id'],
        capture_output=True, text=True)
    if running.stdout.strip():
        raise RuntimeError('WARNO is running; no build started')
    subprocess.run([sys.executable, str(DEV / 'apply_smoke_profile.py')], check=True)
    source = json.loads((DEV / 'smoke-source.json').read_text())
    before = protected_files()
    prior_ai = sha(MOD / 'Gen/NDF/GFX/Skirmish.ndfbin')
    commands = [
        [str(ROOT / 'WARNO.exe'), '-headless', '-nodialogbox', '-nocrashrpt', '-c', '-',
         '-generatemod', 'BattleAtmosphere', '-rootdata', '.',
         'CommonData:Clusters/Bootstrap/ClusterBootstrapGeneration.ndf'],
        [str(ROOT / 'Tools/AssetCooker.exe'), '-e', 'ProgDir:/CoreCatalog.cat', '-g', './Gen/',
         '--common-data', './CommonData/', '--game-data', './GameData/'],
    ]
    results = []
    for i, command in enumerate(commands):
        log = DEV / ('smoke-build-%s.log' % i)
        print('START', Path(command[0]).name, flush=True)
        with log.open('wb') as out:
            p = subprocess.run(command, cwd=MOD, stdout=out, stderr=subprocess.STDOUT, timeout=480)
        results.append(dict(program=Path(command[0]).name, returncode=p.returncode,
                            log=log.name, log_sha256=sha(log)))
        if p.returncode:
            raise RuntimeError(log.read_text(encoding='utf-8', errors='replace')[-5000:])
        print('PASS', Path(command[0]).name, flush=True)
    assert before == protected_files()
    assert sha(MOD / 'Gen/NDF/GFX/Skirmish.ndfbin') == prior_ai, 'AI binary changed'
    for path, digest in source['sources'].items():
        assert sha(MOD / path) == digest
    outputs = {p.relative_to(MOD).as_posix(): sha(p) for p in (MOD / 'Gen').rglob('*')
               if p.is_file() and p.suffix != '.tag'}
    result = dict(version='smoke-preview.1', status='official-build-passed; not-installed; visual-unverified',
                  built_at=datetime.now(timezone.utc).isoformat(), commands=results, sources=source['sources'],
                  protected=before, ai_ndf_sha256=prior_ai, outputs=outputs)
    (DEV / 'smoke-build.json').write_text(json.dumps(result, indent=2) + '\n')
    print('PASS official compilation, packaging and unchanged AI', flush=True)

if __name__ == '__main__':
    main()
