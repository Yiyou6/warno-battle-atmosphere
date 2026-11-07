"""Read only pinned WARNO mod metadata. Requires explicit user authorization.

No writes, debugger attachment, code injection, thread control, or general dump.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
from pathlib import Path
import struct


class Module(C.Structure):
    _fields_ = [('dwSize', W.DWORD), ('th32ModuleID', W.DWORD),
                ('th32ProcessID', W.DWORD), ('GlblcntUsage', W.DWORD),
                ('ProccntUsage', W.DWORD), ('modBaseAddr', C.c_void_p),
                ('modBaseSize', W.DWORD), ('hModule', W.HMODULE),
                ('szModule', W.WCHAR * 256), ('szExePath', W.WCHAR * 260)]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--user-authorized', action='store_true', required=True)
    args=parser.parse_args()
    k=C.WinDLL('kernel32', use_last_error=True)
    k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
    k.CloseHandle.argtypes=[W.HANDLE]
    k.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)]
    k.ReadProcessMemory.argtypes=[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)]
    k.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD];k.CreateToolhelp32Snapshot.restype=W.HANDLE
    k.Module32FirstW.argtypes=[W.HANDLE,C.POINTER(Module)]
    k.Module32NextW.argtypes=[W.HANDLE,C.POINTER(Module)]
    process=k.OpenProcess(0x410,False,args.pid)  # QUERY_INFORMATION | VM_READ only
    if not process: raise C.WinError(C.get_last_error())
    def read(address, size):
        if not 0<size<=65536: raise ValueError('Read bound exceeded')
        data=C.create_string_buffer(size);actual=C.c_size_t()
        if not k.ReadProcessMemory(process,address,data,size,C.byref(actual)) or actual.value!=size:
            raise C.WinError(C.get_last_error())
        return data.raw
    def u64(address):return struct.unpack('<Q',read(address,8))[0]
    def string(address):
        pointer=u64(address)
        if not pointer:return ''
        header=read(pointer,48)
        length,capacity=struct.unpack_from('<QQ',header,32)
        if length>1024:raise ValueError('Unexpected mod string length')
        if not length:return ''
        data=struct.unpack_from('<Q',header,16)[0] if capacity>=16 else pointer+16
        return read(data,length).decode('utf-8','replace')
    try:
        path=C.create_unicode_buffer(32768);size=W.DWORD(len(path))
        if not k.QueryFullProcessImageNameW(process,0,path,C.byref(size)):raise C.WinError(C.get_last_error())
        root=Path(__file__).resolve().parents[3]
        if Path(path.value).resolve()!=root/'WARNO.exe':raise ValueError('Unexpected process executable path')
        digest=hashlib.sha256(Path(path.value).read_bytes()).hexdigest()
        if digest!='70f34d844ebf23eea92d535fad0fffb6e0bc60dd1f64cc80c2b903d06abab3a8':raise ValueError('Unknown executable version')
        snapshot=k.CreateToolhelp32Snapshot(0x18,args.pid)
        if snapshot==C.c_void_p(-1).value:raise C.WinError(C.get_last_error())
        try:
            module=Module();module.dwSize=C.sizeof(module);found=k.Module32FirstW(snapshot,C.byref(module));base=None
            while found:
                if module.szModule.lower()=='warno.exe':base=module.modBaseAddr;break
                found=k.Module32NextW(snapshot,C.byref(module))
            if not base:raise ValueError('Main module not found')
        finally:k.CloseHandle(snapshot)
        manager=u64(base+0x31a6a90);header=read(manager,0x98)
        count=struct.unpack_from('<I',header,0x48)[0];items=struct.unpack_from('<Q',header,0x40)[0]
        if count>128:raise ValueError('Unexpected mod count')
        rows=[]
        for i in range(count):
            address=items+i*0x68;entry=read(address,0x68)
            rows.append(dict(name=string(address+0x10),path=string(address+0x38),
                id=struct.unpack_from('<Q',entry)[0],version=struct.unpack_from('<I',entry,8)[0],
                generation=struct.unpack_from('<I',entry,0x44)[0],
                compatible=bool(entry[0x4b]),parsed=bool(entry[0x4c]),active=bool(entry[0x4d]),
                flags=list(entry[0x48:0x50])))
        rev_count=struct.unpack_from('<I',header,0x30)[0]&0x7ffffff
        rev_items=struct.unpack_from('<Q',header,0x38)[0]
        if rev_count>256:raise ValueError('Unexpected revision count')
        revisions={string(rev_items+i*16):string(rev_items+i*16+8) for i in range(rev_count)}
        result=dict(pid=args.pid,exe_sha256=digest,access='read-only mod metadata',mods=rows,revisions=revisions)
        (Path(__file__).parent/'live-mod-compatibility.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
    finally:k.CloseHandle(process)


if __name__=='__main__':main()
