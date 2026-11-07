"""Authorized, bounded, read-only positions/owners for the pinned WARNO build.

No game functions, writes, injection, suspension or UI operations.
"""
import argparse, ctypes as C, hashlib, json, struct, datetime
from ctypes import wintypes as W
from pathlib import Path
from read_mod_state import Module

def capture(pid):
    k=C.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD]; k.OpenProcess.restype=W.HANDLE
    k.CloseHandle.argtypes=[W.HANDLE]
    k.ReadProcessMemory.argtypes=[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)]
    k.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD];k.CreateToolhelp32Snapshot.restype=W.HANDLE
    k.Module32FirstW.argtypes=[W.HANDLE,C.POINTER(Module)];k.Module32NextW.argtypes=[W.HANDLE,C.POINTER(Module)]
    h=k.OpenProcess(0x410,False,pid)
    if not h:raise C.WinError(C.get_last_error())
    def read(p,n):
        if not p or not 0<n<=65536:raise ValueError('bounded read')
        buf=C.create_string_buffer(n);got=C.c_size_t()
        if not k.ReadProcessMemory(h,p,buf,n,C.byref(got)) or got.value!=n:raise C.WinError(C.get_last_error())
        return buf.raw
    def u64(p):return struct.unpack('<Q',read(p,8))[0]
    def u32(p):return struct.unpack('<I',read(p,4))[0]
    try:
        snap=k.CreateToolhelp32Snapshot(0x18,pid)
        if snap==C.c_void_p(-1).value:raise C.WinError(C.get_last_error())
        modules=[]
        try:
            m=Module();m.dwSize=C.sizeof(m);ok=k.Module32FirstW(snap,C.byref(m))
            while ok:
                modules.append((m.szModule,m.szExePath,m.modBaseAddr))
                ok=k.Module32NextW(snap,C.byref(m))
        finally:k.CloseHandle(snap)
        name,path,base=next(m for m in modules if m[0].lower()=='warno.exe')
        root=Path(__file__).resolve().parents[3]
        if Path(path).resolve()!=root/'WARNO.exe':raise ValueError('wrong executable path')
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!='70f34d844ebf23eea92d535fad0fffb6e0bc60dd1f64cc80c2b903d06abab3a8':raise ValueError('unknown executable')
        lst=u64(base+0x3389840);pn=u32(lst+0x28)
        if not 0<pn<=32:raise ValueError('player count')
        players=struct.unpack('<'+'Q'*pn,read(u64(lst+0x20),pn*8))
        def component(uid,kind,entity,world):
            registry=base+0x31f86e0+world*0xc7580
            bit=entity*255+kind
            if not u32(registry+0xc73a0+(bit//32)*4)&(1<<(bit%32)):return 0
            store=registry+entity*0xc738+0x20+kind*0xc8
            high=uid>>32;index=(high>>8)&0x7fffff
            offset=0x20 if high&0x80000000 else 8
            if index>=u32(store+offset+8):return 0
            return u64(u64(store+offset)+index*8)&~1
        worlds=[]
        for world in range(3):
            rows=[];descriptors=[];errors=0
            for owner in players:
                try:
                    pc=component(owner,0x81,2,world);ul=component(owner,0x86,2,world)
                    if not pc or not ul:continue
                    info=read(pc,0x80);alliance,difficulty,index=struct.unpack_from('<iii',info,0x3c)
                    n=u32(ul+0x20)
                    if n>4096:raise ValueError('unit count')
                    descriptors.append(dict(owner=owner,alliance=alliance,difficulty=difficulty,index=index,count=n,fields=info[0x18:].hex()))
                    ids=struct.unpack('<'+'Q'*n,read(u64(ul+0x18),n*8)) if n else []
                    for uid in ids:
                        try:
                            own=component(uid,0x61,0,world);sp=component(uid,0x6b,0,world)
                            if not own or not sp or u64(own+0x18)!=owner:continue
                            rows.append([uid,owner,alliance,difficulty,index,*struct.unpack('<3f',read(sp+0x30,12))])
                        except (OSError,ValueError):errors+=1
                except (OSError,ValueError):errors+=1
            if rows:worlds.append(dict(world=world,players=descriptors,rows=rows,read_errors=errors))
        result=dict(pid=pid,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),access='QUERY_INFORMATION | VM_READ',modules=[m for m in modules if m[0].lower() in ('warno.exe','version.dll')],worlds=worlds)
        dest=Path(__file__).with_name('live-front-%s-%s.json'%(pid,datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')))
        dest.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(dict(path=str(dest),worlds=[dict(world=w['world'],players=w['players'],units=len(w['rows']),errors=w['read_errors']) for w in worlds]),indent=2))
    finally:k.CloseHandle(h)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pid',type=int,required=True);p.add_argument('--user-authorized',action='store_true',required=True)
    capture(p.parse_args().pid)
