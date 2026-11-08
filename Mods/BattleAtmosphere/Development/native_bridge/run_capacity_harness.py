"""Compile exact production function bodies with isolated fake engine data."""
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys

BASE = Path(__file__).resolve().parent
source = (BASE/'probe_bridge.c').read_text(encoding='utf-8')
def function(name):
    start = re.search(r'^static [^\n]*\b' + re.escape(name) + r'\([^\n]*\) \{', source, re.M).start()
    end = source.index('\n}\n', start) + 3
    return source[start:end]
generated = '\n'.join(function(n) for n in ('native_ai_owner', 'expire_leases', 'lease_ai_unit', 'world_unit_snapshot'))
(BASE/'capacity_functions.generated.h').write_text(generated, encoding='utf-8')
compiler = Path(os.environ['TEMP'])/'codex-warno-compiler/tcc/tcc.exe'
exe = BASE/'capacity_harness.exe'
subprocess.run([str(compiler), '-Wall', '-o', str(exe), str(BASE/'capacity_harness.c')], check=True)
r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)
receipt = {'returncode': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr,
           'extracted_sha256': hashlib.sha256(generated.encode()).hexdigest(),
           'source_sha256': hashlib.sha256((BASE/'probe_bridge.c').read_bytes()).hexdigest(),
           'scope': 'standalone production-function logic with stubbed engine data; no WARNO process'}
dest = BASE.parent/(sys.argv[1] if len(sys.argv)>1 else 'skirmish20-capacity.json')
dest.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
print(r.stdout)
sys.exit(r.returncode)
