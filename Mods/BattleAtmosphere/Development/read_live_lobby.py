"""Read only revision-pinned lobby counts; no names, decks, writes or UI control."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
from pathlib import Path
import struct
import time
from read_mod_state import Module


class Region(C.Structure):
    _fields_ = [('BaseAddress', C.c_void_p), ('AllocationBase', C.c_void_p),
                ('AllocationProtect', W.DWORD), ('PartitionId', W.WORD),
                ('RegionSize', C.c_size_t), ('State', W.DWORD),
                ('Protect', W.DWORD), ('Type', W.DWORD)]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid', type=int, required=True)
    p.add_argument('--user-authorized', action='store_true', required=True)
    p.add_argument('--start', type=lambda s:int(s,0), default=0)
    args = p.parse_args()
    k = C.WinDLL('kernel32', use_last_error=True)
    k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]; k.OpenProcess.restype = W.HANDLE
    k.CloseHandle.argtypes = [W.HANDLE]
    k.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
    k.VirtualQueryEx.argtypes = [W.HANDLE, C.c_void_p, C.POINTER(Region), C.c_size_t]
    k.VirtualQueryEx.restype = C.c_size_t
    k.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]; k.CreateToolhelp32Snapshot.restype = W.HANDLE
    k.Module32FirstW.argtypes = [W.HANDLE, C.POINTER(Module)]
    k.Module32NextW.argtypes = [W.HANDLE, C.POINTER(Module)]
    h = k.OpenProcess(0x410, False, args.pid)
    if not h: raise C.WinError(C.get_last_error())
    def read(at, size):
        if not 0 < size <= 1048576: raise ValueError('Read bound')
        b = C.create_string_buffer(size); got = C.c_size_t()
        if not k.ReadProcessMemory(h, at, b, size, C.byref(got)) or got.value != size:
            raise OSError('Unreadable candidate')
        return b.raw
    def u32(b, off): return struct.unpack_from('<I', b, off)[0]
    def u64(b, off): return struct.unpack_from('<Q', b, off)[0]
    try:
        snap = k.CreateToolhelp32Snapshot(0x18, args.pid)
        if snap == C.c_void_p(-1).value: raise C.WinError(C.get_last_error())
        try:
            m = Module(); m.dwSize = C.sizeof(m); found = k.Module32FirstW(snap, C.byref(m)); base = None
            while found:
                if m.szModule.lower() == 'warno.exe':
                    base = m.modBaseAddr; path = Path(m.szExePath); break
                found = k.Module32NextW(snap, C.byref(m))
            if base is None: raise ValueError('WARNO module missing')
        finally: k.CloseHandle(snap)
        root = Path(__file__).resolve().parents[3]
        if path.resolve() != root / 'WARNO.exe': raise ValueError('Unexpected path')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != '70f34d844ebf23eea92d535fad0fffb6e0bc60dd1f64cc80c2b903d06abab3a8':
            raise ValueError('Unknown executable')
        needles = {'room': struct.pack('<Q', base+0x2482e68), 'ui': struct.pack('<Q', base+0x2444b18)}
        hits = {key: set() for key in needles}
        address = args.start; scanned = 0; started = time.monotonic()
        while address < 0x7fffffffffff and scanned < 8*1024**3 and time.monotonic()-started < 45:
            r = Region()
            if not k.VirtualQueryEx(h, address, C.byref(r), C.sizeof(r)): break
            end = (r.BaseAddress or 0)+r.RegionSize
            if end <= address: break
            if r.State == 0x1000 and r.Type == 0x20000 and r.Protect in (4, 8, 0x40, 0x80):
                for at in range(r.BaseAddress, end, 1048576):
                    if scanned >= 8*1024**3 or time.monotonic()-started >= 45:
                        end=at;break
                    try: data = read(at, min(1048576, end-at))
                    except OSError: continue
                    scanned += len(data)
                    for key, needle in needles.items():
                        pos = data.find(needle)
                        while pos >= 0:
                            if (at+pos) % 8 == 0: hits[key].add(at+pos)
                            pos = data.find(needle, pos+8)
            address = end
        rooms = []; controllers = []
        for at in sorted(hits['room']):
            try:
                b = read(at, 0x210); count = u32(b, 0x60)&0x7ffffff
                if count > 40 or u32(b, 0x13c) > 40 or b[0x130] > 1: continue
                rows = read(u64(b, 0x68), count*0x88) if count else b''
                rooms.append(dict(address=hex(at), network=b[0x130], host=b[0x1a8],
                    max_players=u32(b, 0x134), min_players=u32(b, 0x138), capacity=u32(b, 0x13c),
                    nb_ai=u32(b, 0x170), roster_count=count,
                    roster=[dict(alliance=u32(rows,i*0x88+0x3c),flag=rows[i*0x88+0x40],
                                 ai_level=u32(rows,i*0x88+0x48)) for i in range(count)]))
            except (OSError, ValueError): pass
        for at in sorted(hits['ui']):
            try:
                b = read(at, 0x1f0); count = u32(b, 0x50)
                if count > 40: continue
                slots = []
                for i in range(count):
                    row = u64(read(u64(b,0x48)+8*i,8),0)
                    rb = read(row,0xd0)
                    view = read(u64(rb,0x28),0x108)
                    panels = {}
                    for name, off in (('player',0xe8),('open',0xf0),('closed',0xf8)):
                        widget=u64(view,off)
                        panels[name]=read(widget,0x40)[0x36] if widget else None
                    slots.append(dict(index=i, player_id=u32(rb,0xb8), slot_kind=u32(rb,0xbc),
                                      panel_visible=panels))
                controllers.append(dict(address=hex(at),room=hex(u64(b,0x28)),allocated=count,
                                        cached_visible_budget=u32(b,0x1e0),slots=slots))
            except (OSError, ValueError): pass
        result = dict(pid=args.pid, exe_sha256=digest, access='QUERY_INFORMATION | VM_READ only',
                      scan_start=hex(args.start), scan_next=hex(address), base=hex(base),
                      scanned_bytes=scanned, elapsed_seconds=round(time.monotonic()-started,2),
                      rooms=rooms, controllers=controllers)
        out = Path(__file__).with_name('live-lobby-%s.json'%args.pid)
        out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,indent=2))
    finally: k.CloseHandle(h)


if __name__ == '__main__': main()
