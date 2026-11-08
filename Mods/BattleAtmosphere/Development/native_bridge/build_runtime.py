"""Build the pinned automatic skirmish runtime. Does not install or launch it."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

base=Path(__file__).resolve().parent
root=base.parents[3]
tcc=Path(os.environ['TEMP'])/'codex-warno-compiler/tcc/tcc.exe'
subprocess.run([sys.executable,str(base/'embed_python.py')],check=True)
subprocess.run([sys.executable,str(base/'build_lobby_fixtures.py')],check=True,env=dict(os.environ,PYTHONPATH=str(base.parent)))
subprocess.run([str(tcc),'-shared','-Wall','-DBA_EMBEDDED','-DBA_PROXY','-o',
                str(base/'version.dll'),str(base/'probe_bridge.c'),str(base/'version_proxy.c')],check=True)
inputs=[base/'probe_bridge.c',base/'version_proxy.c',base/'embedded_python.h',base/'fx_budget.h',base/'skirmish_lobby.h',base/'lobby_selftest.h',base/'lobby_fixtures.h']
inputs+=list((root/'Mods/BattleAtmosphere/Runtime/Python').glob('*.py'))
inputs.append(root/'Mods/BAScriptProbe/AutoRuntimeRoot/CommonData/Python/Eugen/ba_fixture.py')
manifest={'status':'spatial-runtime-preview.6+vfx-budget.3+skirmish10.3','game_revision':201602,
          'exe_sha256':'70f34d844ebf23eea92d535fad0fffb6e0bc60dd1f64cc80c2b903d06abab3a8',
          'dll_sha256':hashlib.sha256((base/'version.dll').read_bytes()).hexdigest(),
          'source_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}}
(root/'Mods/BattleAtmosphere/Runtime/build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('BUILT',manifest['dll_sha256'])
