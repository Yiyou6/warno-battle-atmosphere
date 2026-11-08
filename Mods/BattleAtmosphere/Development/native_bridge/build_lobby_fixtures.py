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
    # UI excess-seat arithmetic is a separate path from room allocation.
    native=n.pe.get_data(0x13a7d7c,12)
    assert native==bytes.fromhex('8b8dbc0000000348144129cf')
    # (controller, ai_count): recreate the registers/stack used by that path.
    prologue=bytes.fromhex('555641574881ec000100004889e54889ce448b7e50488b46284805200100008995bc000000')
    epilogue=bytes.fromhex('4489f84881c400010000415f5e5dc3')
    code=prologue+native+epilogue
    rows.append('static const unsigned char lobby_ui_fixture[]={%s};'%','.join('0x%02x'%b for b in code))
    rows.append('static const unsigned lobby_ui_fixture_site=%d;'%len(prologue))
    getter=n.pe.get_data(0x15ceeb0,13)
    assert getter==bytes.fromhex('554889e5488d81200100005dc3')
    rows.append('static const unsigned char lobby_getter_fixture[]={%s};'%','.join('0x%02x'%b for b in getter))
    target=BASE/'lobby_fixtures.h'
    target.write_text('/* Generated from the pinned EXE; owned-headless tests only. */\n'+'\n'.join(rows)+'\n')
    print('Native capacity fixture blocks extracted')

if __name__=='__main__':build()
