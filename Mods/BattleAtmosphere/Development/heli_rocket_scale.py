"""Isolate helicopter rocket presentation while preserving shared ground FX."""
import re
from explosion_scale import scale

VISUAL_SCALE = 1.5
PREFIX = 'BA_HeloSmall_'


def extend(z, before, after, definitions, visuals):
    aliases = {}
    exports = {}
    declarations = []
    for alias in sorted(set(visuals.values())):
        text = definitions[alias]
        for name in sorted(set(re.findall(r'\$/GFX/GameFx/(\w+)', text))):
            path = 'GameData/Fx/Generated/' + name + '.ndf'
            original = z.read(path).decode('utf-8-sig').replace('\r\n', '\n')
            clone, changes = scale(original, visual_scale=VISUAL_SCALE, spatial_scale=VISUAL_SCALE)
            assert changes and path in after
            replacement = PREFIX + name
            assert clone.count('export ' + name + ' is ') == 1
            clone = clone.replace('export ' + name + ' is ', 'export ' + replacement + ' is ', 1)
            after[path] += '\n\n' + clone
            exports[replacement] = name
            text = text.replace('$/GFX/GameFx/' + name, '$/GFX/GameFx/' + replacement)
        renamed = PREFIX + alias
        declarations.append(text.replace(alias + ' is ', renamed + ' is ', 1))
        aliases[alias] = renamed
    assert len(exports) == 10
    return {s: aliases[a] for s, a in visuals.items()}, '\n\n'.join(declarations), exports
