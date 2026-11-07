"""Install the verified visual layer while preserving the current AI/runtime."""
from pathlib import Path
from datetime import datetime, timezone
import json
import subprocess
import sys
from apply_smoke_profile import DEV, MOD, ROOT, sha, protected_files

def main():
    running = subprocess.run(['powershell', '-NoProfile', '-Command',
        'Get-Process WARNO -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id'],
        capture_output=True, text=True)
    if running.stdout.strip():
        raise RuntimeError('WARNO is running; no installation started')
    subprocess.run([sys.executable, str(DEV / 'verify_smoke_profile.py')], check=True)
    checked = json.loads((DEV / 'smoke-verification.json').read_text())
    saved = Path.home() / 'Saved Games/EugenSystems/WARNO/mod/BattleAtmosphere'
    activation = saved.parent / 'Config.ini'
    active_before = activation.read_bytes()
    before = protected_files()
    sys.path.insert(0, str(DEV / 'native_bridge'))
    from verify_runtime import check_local_mod_identity
    identity = check_local_mod_identity()
    subprocess.run([sys.executable, str(ROOT / 'Mods/Utils/Scripts/CopyModGenData.py'),
                    'WARNO', 'BattleAtmosphere'], cwd=MOD, check=True)
    for path, digest in checked['outputs'].items():
        assert sha(saved / path) == digest, path
    assert sha(saved / 'Gen/NDF/GFX/Skirmish.ndfbin') == sha(MOD / 'Gen/NDF/GFX/Skirmish.ndfbin')
    assert before == protected_files() and activation.read_bytes() == active_before
    assert identity == check_local_mod_identity()
    result = dict(version='smoke-preview.1', status='installed; rendered-appearance-and-frame-rate-unverified',
                  installed_at=datetime.now(timezone.utc).isoformat(), outputs=checked['outputs'],
                  config_sha256=sha(saved / 'Config.ini'), runtime_dll_sha256=sha(ROOT / 'version.dll'),
                  ai_unchanged=True, gameplay_smoke_and_fire_unchanged=True,
                  compiled_calls=checked['compiled_calls'], backup='archive/smoke-preview1-before.zip')
    (DEV / 'smoke-release.json').write_text(json.dumps(result, indent=2) + '\n')
    print('INSTALLED smoke-preview.1; current AI and runtime preserved')

if __name__ == '__main__':
    main()
