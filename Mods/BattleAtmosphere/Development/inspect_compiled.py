"""Inspect selected scalar signatures in this build's CNDF v2 payload.

This is deliberately not a full NDF interpreter. It checks named property table
entries and unique typed scalar signatures inside OBJE; it proves packaging,
not runtime loading or behavior. Requires zstandard with the executing Python.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_info import VERSION

ROOT = Path(__file__).resolve().parents[1]


def inspect(path):
    try:
        import zstandard
    except ImportError:
        sys.path.insert(0, str(Path(os.environ.get('TEMP', '.')) / 'codex-warno-zstd'))
        import zstandard
    raw = path.read_bytes()
    if raw[:16] != b'EUG0\x01\x00\x00\x00CNDF\x02\x00\x00\x00' or raw[44:48] != bytes.fromhex('28 b5 2f fd'):
        raise ValueError('Unknown binary format; review before interpreting')
    body = zstandard.ZstdDecompressor().decompress(raw[44:], max_output_size=32*1024*1024)
    u32 = lambda offset: struct.unpack_from('<I', body, offset)[0]
    toc = struct.unpack_from('<Q', raw, 16)[0] - 40
    if body[toc:toc+4] != b'TOC0':
        raise ValueError('Invalid table directory')
    tables = {}
    for i in range(u32(toc+4)):
        p = toc + 8 + 24*i
        name = body[p:p+8].rstrip(b'\0').decode('ascii')
        offset, size = struct.unpack_from('<QQ', body, p+8)
        offset -= 40
        if offset < 0 or offset+size > toc:
            raise ValueError('Section outside payload: ' + name)
        tables[name] = (offset, size)
    p, size = tables['PROP']
    end = p+size
    properties = []
    while p < end:
        length = u32(p)
        p += 4
        if p+length+4 > end:
            raise ValueError('Invalid property name length')
        name = body[p:p+length].rstrip(b'\0').decode('utf-8')
        p += length
        class_id = u32(p)
        p += 4
        properties.append((name, class_id))
    start, size = tables['OBJE']
    objects = body[start:start+size]
    expected = {
        'UseAntiStackingForVehicles': (0, True),
        'UseAntiStackingForInfantry': (0, True),
        'DontUseRegroupPoint': (0, True),
        'MaxNumberOfStackingUnits': (3, 1),
        'MergeGroupDistInPolygon': (5, 1.0),
        'AddToGroupDistInPolygon': (5, 0.75),
        'DistToValidateRegroupPointInPolygon': (5, 1.5),
        'BlitzkriegMultiplierForTacticalPathInCover': (5, 2.0),
        'CanSelectTransportUnits': (0, True),
        'MinUnitWeightToReserveCorridor': (5, 15.0),
        'TimeToWaitAfterFleeToGoBackToOriginalPositionInSeconds': (5, 7.5),
        'MinLifeRatioForRetreat': (5, 0.3),
        'TargetPowerForOpportunisticSingleTargetAirStrike': (5, 70.0),
        'TargetPowerForOpportunisticTargetInGroupAirStrike': (5, 60.0),
    }
    findings = {}
    for name, (type_id, value) in expected.items():
        ids = [(i,c) for i,(n,c) in enumerate(properties) if n==name]
        if len(ids)!=1:
            raise ValueError('Expected one property definition: '+name)
        i,c = ids[0]
        prefix = struct.pack('<II',i,type_id)
        payload = struct.pack({0:'<?',3:'<i',5:'<f'}[type_id],value)
        signature = prefix+payload
        count = objects.count(signature)
        if count!=1:
            raise ValueError('Expected one typed scalar signature for '+name+', got '+str(count))
        findings[name] = {'property_id':i,'class_id':c,'value':value,
                          'object_section_offset':objects.index(signature),'signature_matches':count}
    for export in ['VeryHardStrategy','Artillery_Support_Autogen','Attack_Frontage_BA','Attack_Frontage_Reinforce_BA','Defense_Frontage_BA','Attack_Main_BA','Attack_Objectives_BA']:
        if export.encode() not in body:
            raise ValueError('Expected exported name absent: '+export)
    return {'version':VERSION,'format':'CNDF v2','evidence':'property table plus unique typed scalar signatures; not runtime',
            'file_sha256':hashlib.sha256(raw).hexdigest(),'compressed_bytes':len(raw),
            'expanded_bytes':len(body),'selected_scalars':findings}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('file',nargs='?',default=str(ROOT/'Gen/NDF/GFX/Skirmish.ndfbin'))
    args=parser.parse_args()
    result=inspect(Path(args.file))
    (ROOT/'Development/compiled-validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('PASS: named global AI constants are present in the generated GFX/Skirmish payload.')
    print('Native anti-stacking and forward-screen settings packaged; retreat and airstrike controls preserved.')
    print('Payload SHA256:',result['file_sha256'])


if __name__=='__main__':
    main()
