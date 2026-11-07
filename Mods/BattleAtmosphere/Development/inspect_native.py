"""Read-only native registration/disassembly navigator for this WARNO build."""
import bisect
import os
from pathlib import Path
import re
import struct
import sys

sys.path.insert(0, str(Path(os.environ['TEMP']) / 'codex-warno-nativeaudit'))
import pefile
import capstone


class Native:
    def __init__(self):
        self.path = Path(__file__).resolve().parents[3] / 'WARNO.exe'
        self.raw = self.path.read_bytes()
        self.pe = pefile.PE(data=self.raw, fast_load=True)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        sec = next(s for s in self.pe.sections if s.Name.startswith(b'.pdata'))
        data = sec.get_data()[:sec.Misc_VirtualSize]
        self.functions = [struct.unpack_from('<III', data, i) for i in range(0, len(data)-11, 12)]
        self.starts = [f[0] for f in self.functions]
        self.dis = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.dis.detail = True
        self.refs = {}
        for s in self.pe.sections:
            if not s.Characteristics & 0x20000000:
                continue
            for m in re.finditer(rb'[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d].{4}', s.get_data(), re.S):
                r = s.VirtualAddress + m.start()
                target = r + 7 + struct.unpack('<i', m.group()[-4:])[0]
                self.refs.setdefault(target, []).append(r)

    def string(self, rva):
        try:
            s = self.pe.get_string_at_rva(rva, max_length=220).decode('ascii')
            return s if len(s) > 2 and all(32 <= ord(c) < 127 for c in s) else ''
        except Exception:
            return ''

    def references(self, name):
        out = []
        for m in re.finditer(re.escape(name.encode('ascii') + b'\0'), self.raw):
            target = self.pe.get_rva_from_offset(m.start())
            for ref in self.refs.get(target, []):
                out.append((ref, target))
        return out

    def bounds(self, rva):
        i = bisect.bisect_right(self.starts, rva)-1
        if i >= 0 and self.functions[i][0] <= rva < self.functions[i][1]:
            return self.functions[i][:2]
        return rva, rva+256

    def show(self, start, end=None, names_only=False):
        if end is None:
            start, end = self.bounds(start)
        print('FUNCTION', hex(start), hex(end))
        for ins in self.dis.disasm(self.pe.get_data(start, end-start), self.base+start):
            suffix = ''
            for op in ins.operands:
                if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                    target = ins.address + ins.size + op.mem.disp-self.base
                    s = self.string(target)
                    if s:
                        suffix += ' ; '+repr(s)
            if not names_only or suffix:
                print(hex(ins.address-self.base), ins.mnemonic, ins.op_str, suffix)


if __name__ == '__main__':
    n = Native()
    for arg in sys.argv[1:]:
        if arg.startswith('0x'):
            n.show(int(arg, 16))
        else:
            print('NAME', arg)
            for ref, target in n.references(arg):
                print('REF', hex(ref), 'STR', hex(target))
                n.show(ref, names_only=True)
