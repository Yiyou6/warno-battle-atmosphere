"""Read-only, build-locked evidence for native fields omitted by shipped NDF.

Uses PE virtual addresses and registration/constructor instructions. This does
not patch the executable, attach to a process or prove runtime behavior.
Dependencies are isolated under TEMP/codex-warno-nativeaudit.
"""
from pathlib import Path
import hashlib
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
EXE_SHA = '70f34d844ebf23eea92d535fad0fffb6e0bc60dd1f64cc80c2b903d06abab3a8'


def main():
    sys.path.insert(0, str(Path(os.environ['TEMP'])/'codex-warno-nativeaudit'))
    import pefile
    import capstone
    exe = ROOT.parents[1]/'WARNO.exe'
    raw = exe.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=EXE_SHA:
        raise SystemExit('Executable changed; re-discover registrations instead of trusting old RVAs')
    pe = pefile.PE(data=raw, fast_load=True)
    image_base = pe.OPTIONAL_HEADER.ImageBase
    dis = capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
    dis.detail = True

    def instructions(rva, size):
        return list(dis.disasm(pe.get_data(rva,size),image_base+rva))

    def named_lea(rva, expected):
        ins = instructions(rva,7)[0]
        assert ins.mnemonic=='lea' and ins.operands[-1].mem.base==capstone.x86.X86_REG_RIP
        target=ins.address+ins.size+ins.operands[-1].mem.disp-image_base
        name=pe.get_string_at_rva(target).decode('ascii')
        assert name==expected,(hex(rva),name,expected)
        return name

    # Class registrations connect the specific descriptor to the common one.
    named_lea(0xca8a8d,'TIAStratConstantesDescriptor_Specific')
    named_lea(0xd8836d,'TIAStratConstantesDescriptor')
    named_lea(0xd705ed,'TDefenseBehaviorSettingHolder')
    common = instructions(0xd88fd0,445)
    assert any(i.mnemonic=='movups' and i.op_str=='xmmword ptr [rsi + 0x62], xmm0' for i in common)
    assert any(i.mnemonic=='xorps' and i.op_str=='xmm0, xmm0' for i in common)
    defense = instructions(0xd70660,108)
    assert any(i.mnemonic=='mov' and i.op_str=='dword ptr [rax + 0x3f], 0' for i in defense)

    rows=[]
    for name,rva,offset,owner in [
        ('UseAntiStackingForVehicles',0xd88784,0x70,'TIAStratConstantesDescriptor'),
        ('UseAntiStackingForInfantry',0xd887a6,0x71,'TIAStratConstantesDescriptor'),
        ('DontUseRegroupPoint',0xd70762,0x40,'TDefenseBehaviorSettingHolder'),
    ]:
        named_lea(rva,name)
        seq=instructions(rva,0x17)
        assert any(i.mnemonic=='mov' and i.op_str==f'edx, 0x{offset:x}' for i in seq)
        assert any(i.mnemonic=='call' and i.op_str==hex(image_base+0x8b5c0) for i in seq)
        rows.append({'field':name,'owner':owner,'field_offset':hex(offset),
                     'registration_rva':hex(rva),'native_constructor_initial_value':False,
                     'evidence':'bool registration and zero initialization covering the field offset'})
    named_lea(0xb96162,'AntiStackingMaxCellDistance')
    report={'executable_sha256':EXE_SHA,'scope':'read-only static native evidence, not runtime execution',
            'fields':rows,'rejected_candidates':[
                {'field':'AntiStackingMaxCellDistance','reason':'Registration is alongside strategic pawns, action points and campaign battle settings; not used for skirmish dispersion.'}],
            'limitations':['Native constructor defaults may be overridden at runtime.',
                           'DontUseRegroupPoint belongs to defense behavior, not a universal attack-regroup switch.',
                           'Field availability and compilation do not prove full-front coverage or artillery survival.']}
    (ROOT/'Development/native-field-audit.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('PASS: 3 native boolean fields, class ownership and constructor-zero evidence; executable unchanged.')


if __name__=='__main__':
    main()
