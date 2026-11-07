"""Read-only EDAT v2/v3 index inspector. Never loads or executes archive code.

Format cross-checked against kilivan4iK/moddingSuite, BL/EdataManager.cs and
Model/Edata/EdataHeader.cs (MIT). This implementation only supports inspection;
it intentionally has no archive-writing API.
"""
from pathlib import Path
import struct


class Edat:
    def __init__(self, path):
        self.path = Path(path)
        with self.path.open('rb') as stream:
            header = stream.read(80)
            if header[:4] != b'edat':
                raise ValueError('Not EDAT')
            self.version, = struct.unpack_from('<I', header, 4)
            if self.version == 2:
                offset, length, self.data_offset = struct.unpack_from('<III', header, 25)
            elif self.version == 3:
                offset, length, self.data_offset = struct.unpack_from('<IIQ', header, 8)
            else:
                raise ValueError('Unsupported EDAT version')
            if length > 64 * 1024 * 1024 or offset + length > self.data_offset:
                raise ValueError('Invalid index bounds')
            stream.seek(offset)
            index = stream.read(length)
        self.files = self._index(index)

    def _index(self, data):
        # Current WARNO archives use unpadded names, including observed v2 packs.
        pos = 0
        stack = []
        out = {}
        size = self.path.stat().st_size
        while pos < len(data):
            while stack and pos == stack[-1][0]:
                stack.pop()
            start = pos
            kind, span = struct.unpack_from('<II', data, pos)
            pos += 8
            if not kind:
                rel, count = struct.unpack_from('<QQ', data, pos)
                pos += 32  # offsets + MD5
            end = data.index(b'\0', pos)
            name = data[pos:end].decode('utf-8')
            pos = end + 1
            if kind:
                limit = start + span if span else (stack[-1][0] if stack else len(data))
                if not pos <= limit <= len(data):
                    raise ValueError('Invalid directory span')
                stack.append((limit, name))
            else:
                path = ''.join(p for _, p in stack) + name
                path = path.replace('\\', '/')
                if path in out or self.data_offset + rel + count > size:
                    raise ValueError('Duplicate or out-of-bounds entry: ' + path)
                if span and pos != start + span:
                    raise ValueError('Unsupported name padding or entry layout')
                out[path] = (self.data_offset + rel, count)
        if pos != len(data):
            raise ValueError('Index overrun')
        return out

    def read(self, name, max_bytes=8 * 1024 * 1024):
        offset, count = self.files[name]
        if count > max_bytes:
            raise ValueError('Entry exceeds inspection size bound')
        with self.path.open('rb') as stream:
            stream.seek(offset)
            data = stream.read(count)
        if len(data) != count:
            raise ValueError('Truncated entry')
        return data


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive')
    parser.add_argument('--filter', default='')
    args = parser.parse_args()
    archive = Edat(args.archive)
    for name, (offset, count) in archive.files.items():
        if args.filter.lower() in name.lower():
            print(f'{offset:12d} {count:10d} {name}')
