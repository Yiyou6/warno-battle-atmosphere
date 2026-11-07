"""Read-only endpoint navigation checks in a newly owned headless world."""
from pathlib import Path
import json,os,subprocess,sys,shutil
DEV=Path(__file__).resolve().parent;ROOT=DEV.parents[2];B=DEV/'native_bridge'
sys.path.insert(0,str(B));from verify_runtime import events
def main():
    r=json.loads((DEV/'direction-transport-swapped.json').read_text())
    routes=events(r['stdout'],'TRANSPORT_ROUTE')
    initial=dict((row[0],row) for row in events(r['stdout'],'SPACE_POSITIONS')[0])
    points=[q[-1] for q in routes]+[(initial[q[0]][3],initial[q[0]][4]) for q in routes]
    code="import struct\nimport _ba_native as n\nfrom ba_space import Navigation\ndone=False\npoints="+repr(points)+"\ndef tick():\n    global done\n    if done:return\n    nav=Navigation(n.world_navigation())\n    for p in points:\n        for k in range(4):\n            coarse=nav.valid(k,nav.index(*p))\n            exact=struct.unpack('<i',n.nav_point(struct.pack('<Iff',k,p[0],p[1])))[0]\n            n.log('ENDPOINT_CHECK '+repr((p,k,coarse,exact)))\n    done=True\nn.set_tick_callback(tick)\n"
    literal='"'+''.join('\\%03o'%b for b in code.encode())+'"'
    c='''#define ba_startup ba_runtime_startup
#include "probe_bridge.c"
#undef ba_startup
static void check_start(void *launcher){
 PyObject *result;automatic_start(launcher);
 ((void (*)(void *))(game+0x4bff0))(game+0x3389610);
 decref(tick_callback);tick_callback=NULL;
 result=load_embedded_module("ba_endpoint_check",PYTHON_CODE);
 if(!result){log_line("ENDPOINT_PROBE_FAILED");ExitProcess(74);}decref(result);
 ((void (*)(void *))(game+0x4c000))(game+0x3389610);
}
int ba_startup(void){DWORD old,ignored;void **vtable;
 if(!strstr(GetCommandLineA(),"-headless")||!strstr(GetCommandLineA(),"BattleAtmosphereProbeAutoFixture"))return 0;
 if(!ba_runtime_startup())return 0;vtable=(void **)(game+0x235e118);
 if(!VirtualProtect(vtable+11,8,PAGE_READWRITE,&old))return 0;
 vtable[11]=check_start;VirtualProtect(vtable+11,8,old,&ignored);return 1;
}
'''.replace('PYTHON_CODE',literal)
    source=B/'transport_endpoint_probe.c';source.write_text(c)
    dll=B/'transport_endpoint_probe.dll'
    subprocess.run([str(Path(os.environ['TEMP'])/'codex-warno-compiler/tcc/tcc.exe'),'-shared','-Wall','-DBA_EMBEDDED','-DBA_PROXY','-o',str(dll),str(source),str(B/'version_proxy.c')],check=True)
    boot=ROOT/'Mods/BAScriptProbe/AutoloadBoot/version.dll';previous=boot.read_bytes()
    try:
        shutil.copy2(dll,boot)
        subprocess.run([sys.executable,str(DEV/'run_python_probe.py'),'transport-endpoint-diagnostic.json','--autoload','--stock-data','--autohook','--fixture-camps','--activation-gate','--timeout','100'],check=True,capture_output=True)
    finally:boot.write_bytes(previous)
    result=json.loads((DEV/'transport-endpoint-diagnostic.json').read_text())
    assert result['returncode']==0 and not result['timeout'] and not result['stderr'].strip()
    print(json.dumps(events(result['stdout'],'ENDPOINT_CHECK'),indent=2))
if __name__=='__main__':main()
