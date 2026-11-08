"""Extract the two real native capacity calculations for bounded headless tests.

Keep all native branches/conditions, reroute only their final branch to RET.
The executable is read-only. Both original and patched calculations are run.
"""
from pathlib import Path
import hashlib, struct
from inspect_native import Native

BASE=Path(__file__).resolve().parent

def build():
    n=Native()
    assert hashlib.sha256(n.raw).hexdigest()=='70f34d844ebf23eea92d535fad0fffb6e0bc60dd1f64cc80c2b903d06abab3a8'
    rows=[]
    for index,(start,end,site) in enumerate(((0x15d44b6,0x15d4533,0x15d44bd),
                                            (0x15d59a8,0x15d5a36,0x15d59b6))):
        code=bytearray(n.pe.get_data(start,end-start))
        for ins in n.dis.disasm(bytes(code),start):
            if not ins.mnemonic.startswith('j'):continue
            target=ins.operands[0].imm
            if target>=end:
                at=ins.address-start+ins.imm_offset
                delta=end-(ins.address+ins.size)
                code[at:at+ins.imm_size]=delta.to_bytes(ins.imm_size,'little',signed=True)
            else: assert start<=target<end
        # push rsi; mov rsi,rcx gives the native RSI input and original alignment.
        code=b'\x56\x48\x89\xce'+code+(b'\x89\xc8' if index else b'')+b'\x5e\xc3'
        rows.append('static const unsigned char lobby_fixture_%d[]={%s};' %
                    (index,','.join('0x%02x'%b for b in code)))
        rows.append('static const unsigned lobby_fixture_site_%d=%d;'%(index,4+site-start))
    target=BASE/'lobby_fixtures.h'
    target.write_text('/* Generated from the pinned EXE; owned-headless tests only. */\n'+'\n'.join(rows)+'\n')
    print('Native capacity fixture blocks extracted')

if __name__=='__main__':build()
