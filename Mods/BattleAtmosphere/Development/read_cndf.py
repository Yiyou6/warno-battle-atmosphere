"""Read-only CNDF v2 object graph inspection. Never writes game packages.

Format cross-checked against moddingSuite's MIT NdfbinReader/NdfTypeManager.
Unknown types, invalid references, and partially consumed sections fail closed.
"""
from pathlib import Path
import json
import os
import struct
import sys

sys.path.insert(0, str(Path(os.environ['TEMP']) / 'codex-warno-zstd'))
import zstandard


class Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, size):
        if size < 0 or self.pos + size > len(self.data):
            raise ValueError(('Truncated section', self.pos, size, len(self.data)))
        result = self.data[self.pos:self.pos + size]
        self.pos += size
        return result

    def unpack(self, fmt):
        values = struct.unpack('<' + fmt, self.take(struct.calcsize('<' + fmt)))
        return values[0] if len(values) == 1 else list(values)

    def u32(self):
        return self.unpack('I')

    def string(self):
        return self.take(self.u32()).rstrip(b'\0').decode('utf-8')


class Cndf:
    def __init__(self, raw):
        if raw[:16] != b'EUG0\x01\0\0\0CNDF\x02\0\0\0':
            raise ValueError('Unsupported CNDF header')
        body = zstandard.ZstdDecompressor().decompress(raw[44:], max_output_size=64*1024*1024)
        toc = struct.unpack_from('<Q', raw, 16)[0] - 40
        r = Reader(body[toc:])
        if r.take(4) != b'TOC0':
            raise ValueError('Invalid table directory')
        self.tables = {}
        for _ in range(r.u32()):
            name = r.take(8).rstrip(b'\0').decode('ascii')
            offset, size = r.unpack('QQ')
            offset -= 40
            if offset < 0 or offset + size > toc:
                raise ValueError('Invalid section bounds: ' + name)
            self.tables[name] = body[offset:offset+size]
        self.classes = self.strings('CLAS')
        self.text = self.strings('STRG')
        self.trans = self.strings('TRAN')
        self.props = []
        r = Reader(self.tables['PROP'])
        while r.pos < len(r.data):
            self.props.append((r.string(), r.u32()))
        self.objects = []
        r = Reader(self.tables['OBJE'])
        while r.pos < len(r.data):
            class_id = r.u32()
            obj = {'id': len(self.objects), 'class': self.classes[class_id], 'properties': {}}
            while True:
                prop = r.u32()
                if prop == 0xABABABAB:
                    break
                name, owner = self.props[prop]
                # Inherited properties retain their declaring class ID.
                # Native inheritance is not fully stored in the file.
                if owner >= len(self.classes):
                    raise ValueError(('Invalid property owner', name, owner))
                if name in obj['properties']:
                    raise ValueError('Duplicate property: ' + name)
                obj['properties'][name] = self.value(r)
            self.objects.append(obj)
        expected = struct.unpack_from('<I', self.tables['CHNK'], 4)[0]
        if len(self.objects) != expected:
            raise ValueError(('Object count mismatch', len(self.objects), expected))

    def strings(self, name):
        r = Reader(self.tables.get(name, b''))
        result = []
        while r.pos < len(r.data):
            result.append(r.string())
        return result

    def value(self, r):
        t = r.u32()
        if t == 9:
            t = r.u32()
        formats = {0:'?', 1:'B', 2:'i', 3:'I', 4:'Q', 5:'f', 6:'d',
                   0xB:'fff', 0xC:'ffff', 0xD:'BBBB', 0xE:'iii',
                   0x13:'q', 0x18:'h', 0x19:'H', 0x1F:'ii', 0x21:'ff'}
        if t in formats:
            return r.unpack(formats[t])
        if t in (7, 0x1C):
            return self.text[r.u32()]
        if t == 8:
            return r.take(r.u32()).decode('utf-16le')
        if t == 0xBBBBBBBB:
            instance, cls = r.unpack('II')
            # Native Depiction maps contain explicit null object references.
            if instance == cls == 0xFFFFFFFF:
                return None
            return {'ref': instance, 'class': self.classes[cls]}
        if t == 0xAAAAAAAA:
            index = r.u32()
            # This is an IMPR-tree index, not an index into TRAN strings.
            # Preserve it explicitly until the import tree is decoded.
            return {'import_index': index}
        if t == 0x11:
            return [self.value(r) for _ in range(r.u32())]
        if t == 0x12:
            return {'map': [[self.value(r), self.value(r)] for _ in range(r.u32())]}
        if t == 0x22:
            return {'pair': [self.value(r), self.value(r)]}
        if t in (0x1A, 0x25, 0x1D):
            return {'type': hex(t), 'hex': r.take(8 if t == 0x1D else 16).hex()}
        if t in (0x14, 0x1E):
            size = r.u32()
            flag = r.unpack('B') if t == 0x1E else None
            return {'type': hex(t), 'flag': flag, 'hex': r.take(size).hex()}
        if t == 0xEEEEEEEE:
            return None
        raise ValueError(('Unsupported type', hex(t), 'at', r.pos - 4))

    def describe(self):
        return {'classes': self.classes, 'properties': self.props,
                'strings': self.text, 'transactions': self.trans,
                'objects': self.objects,
                'exports_raw': self.tables.get('EXPR', b'').hex(),
                'imports_raw': self.tables.get('IMPR', b'').hex()}


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) == 3:
        from read_edat import Edat
        raw = Edat(Path(sys.argv[1])).read(sys.argv[2], max_bytes=64*1024*1024)
    else:
        raw = Path(sys.argv[1]).read_bytes()
    print(json.dumps(Cndf(raw).describe(), ensure_ascii=False, indent=2))
