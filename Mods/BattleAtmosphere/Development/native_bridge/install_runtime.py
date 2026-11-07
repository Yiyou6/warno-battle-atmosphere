"""Install only the validated, reversible runtime; never overwrite another loader.

Run from any directory with Python 3. --disable stops the sidecar on next match.
--remove deletes only the DLL named and hash-verified in our install receipt.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

from verify_runtime import BASE, ROOT, RUNTIME, check_local_mod_identity, sha, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--disable', action='store_true')
    group.add_argument('--remove', action='store_true')
    args = parser.parse_args()
    target = ROOT / 'version.dll'
    config = RUNTIME / 'runtime.ini'
    receipt_path = RUNTIME / 'installation.json'
    previous = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
    if args.disable or args.remove:
        if args.remove and target.exists():
            if not previous or sha(target) != previous['dll_sha256']:
                raise RuntimeError('Refusing to remove an unknown version.dll')
            target.unlink()
        config.write_text('[Runtime]\nEnabled=0\n', encoding='ascii')
        print('Runtime disabled' + ('; owned loader removed' if args.remove else ''))
        return
    check_local_mod_identity()
    validated = verify()
    if target.exists():
        owned = {validated['dll_sha256']}
        if previous:
            owned.add(previous['dll_sha256'])
        if sha(target) not in owned:
            raise RuntimeError('Existing version.dll belongs to another tool; it was not changed')
    # Install with no edits to the game's executable, archives, or mod selection.
    # Copy failure (for example a running process) leaves activation untouched.
    if not target.exists() or sha(target) != validated['dll_sha256']:
        shutil.copy2(BASE / 'version.dll', target)
    assert sha(target) == validated['dll_sha256']
    config.write_text('[Runtime]\nEnabled=1\n', encoding='ascii')
    receipt = dict(status='installed-runtime-preview; ordinary-battle-unverified',
                   installed_at=datetime.now(timezone.utc).isoformat(),
                   target=str(target), dll_sha256=sha(target),
                   exe_sha256=sha(ROOT / 'WARNO.exe'), validation=validated,
                   requires_active_mod='BattleAtmosphere')
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    (RUNTIME / 'validation.json').write_text(json.dumps(validated, indent=2) + '\n')
    print(json.dumps({key: value for key, value in receipt.items() if key != 'validation'}, indent=2))


if __name__ == '__main__':
    main()
