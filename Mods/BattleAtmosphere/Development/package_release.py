"""Package the verified local test build without changing activated mods."""
from pathlib import Path
import hashlib
import json
import os
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_info import VERSION, CONFIG_VERSION, DECK_FORMAT_VERSION


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    manifest = json.loads((ROOT/'Development/manifest.json').read_text(encoding='utf-8'))
    audit = json.loads((ROOT/'Development/compiled-validation.json').read_text(encoding='utf-8'))
    static = json.loads((ROOT/'Development/static-validation.json').read_text(encoding='utf-8'))
    if manifest['version'] != VERSION or static['version'] != VERSION or audit['version'] != VERSION:
        raise SystemExit('Validation belongs to a different version')
    binary = ROOT/'Gen/NDF/GFX/Skirmish.ndfbin'
    if audit['file_sha256'] != sha(binary.read_bytes()):
        raise SystemExit('Binary changed since inspection')
    for entry in manifest['files']:
        source = ROOT/entry['path']
        if sha(source.read_bytes()) != entry['modified_sha256']:
            raise SystemExit('Source changed since validation: '+entry['path'])
        if source.stat().st_mtime > binary.stat().st_mtime:
            raise SystemExit('Source is newer than compiled payload: '+entry['path'])
    log = ROOT/('Development/build-v'+VERSION+'.log')
    if 'Mod Generation Success' not in log.read_text(encoding='utf-8-sig'):
        raise SystemExit('No successful official build receipt')
    installed = Path(os.environ['USERPROFILE'])/'Saved Games/EugenSystems/WARNO/mod/BattleAtmosphere'
    activation = installed.parent/'Config.ini'
    activation_before = activation.read_bytes()
    config_path = installed/'Config.ini'
    config = config_path.read_text(encoding='utf-8-sig')
    if not re.search(r'(?m)^Name\s*=\s*BattleAtmosphere\s*$',config) or not re.search(r'(?m)^ID\s*=\s*0\s*(?:;.*)?$',config):
        raise SystemExit('Unexpected installed mod identity; refusing metadata edit')
    archive = ROOT/('Development/archive/Config-before-'+VERSION+'.ini')
    if not archive.exists():
        archive.write_bytes(config_path.read_bytes())
    for key,value in [('Version',CONFIG_VERSION),('DeckFormatVersion',DECK_FORMAT_VERSION)]:
        config,n = re.subn(r'(?m)^('+key+r'\s*=\s*)\d+',lambda m:m[1]+str(value),config)
        if n != 1:
            raise SystemExit('Expected exactly one config key: '+key)
    config_path.write_text(config,encoding='utf-8')
    runtime_dirs = ['Gen/NDF','Gen/TextureProxy','Gen/MeshPack','Gen/ResourceFile','Gen/Localisation']
    files = [config_path]
    for directory in runtime_dirs:
        for p in (installed/directory).rglob('*'):
            if p.is_file() and 'Intermediate' not in p.parts and p.suffix != '.tag':
                files.append(p)
    for p in files:
        relative = p.relative_to(installed)
        if relative.as_posix()=='Config.ini':
            continue
        generated = ROOT/relative
        if not generated.exists() or p.read_bytes()!=generated.read_bytes():
            raise SystemExit('Installed/generated mismatch: '+str(relative))
    hashes = {p.relative_to(installed).as_posix():sha(p.read_bytes()) for p in files}
    usage = f'''BattleAtmosphere {VERSION} - 前线覆盖与原生防堆叠测试包

适用目标：最高难度，征服与歼灭遭遇战。
把 BattleAtmosphere 文件夹放入：Saved Games/EugenSystems/WARNO/mod/
在游戏 Mod Center 启用 BattleAtmosphere，按提示重启，开始新的遭遇战。
本机制作时没有自动修改启用列表，也未停用已有地图模组。

已通过官方生成、源文件检查、70 个默认卡组角色/费用下界检查和生成包核对。
第一版获用户黑森林 4v4 征服反馈：后方无大部队长期闲置，双方高代价争夺已出现。
第二版仍扎堆，未通过分散验收。
本版启用原生步兵/车辆防堆叠，薄前沿与普通攻势按负责通道分配，限制旧主攻团持续吸纳增援。
三个原生字段均经类型核实、官方编译和生成包检查；新增前沿两槽费用含运输，已检查 70 默认卡组。
保留空炮防空、运输和恢复设置。未控制电脑界面；均匀前线与实战效果仍待验证。
大量可用部队长期在后方无事可做，仍判定方案不达标。
突破专用攻守调度保持原版；自定义攻守地图不等于完成兼容测试。
停用：在 Mod Center 取消 BattleAtmosphere 并按提示重启。
'''
    receipt = {'version':VERSION,'status':'built_test_candidate_not_battle_validated',
               'latest_user_feedback':{'version':'0.2.1-test2','result':'仍然扎堆，分散验收不通过',
                   'clarification':'沿前线较均匀分散，少数主攻区适度密集，减少炮火集中毁伤'},
               'prior_user_feedback':{'version':'0.2.0-test1','scenario':'黑森林 4v4 征服',
                   'confirmed':['没有大部队长期停在后方','双方付出巨大代价决出胜者的感觉'],
                   'unresolved':['部队扎堆','进攻战术单一']},
               'baseline_sha256':manifest['baseline_sha256'],'source_files':manifest['files'],
               'runtime_files':hashes,'default_decks_audited':len(static['default_decks']),
               'frontage_screen_costs':static['frontage_screen_costs'],
               'native_field_evidence':json.loads((ROOT/'Development/native-field-audit.json').read_text(encoding='utf-8')),
               'compiled_evidence':audit,'activation_file_sha256':sha(activation_before)}
    dist = ROOT/'dist'
    dist.mkdir(exist_ok=True)
    output = dist/('BattleAtmosphere-'+VERSION+'.zip')
    if output.exists():
        raise SystemExit('Release already exists; preserve it and choose a new version')
    with zipfile.ZipFile(str(output),'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(files):
            z.write(p,'BattleAtmosphere/'+p.relative_to(installed).as_posix())
        z.writestr('BattleAtmosphere/使用说明.txt',usage.encode('utf-8'))
        z.writestr('BattleAtmosphere/验证摘要.json',json.dumps(receipt,ensure_ascii=False,indent=2).encode('utf-8'))
    with zipfile.ZipFile(str(output)) as z:
        if z.testzip() is not None:
            raise SystemExit('Corrupt release archive')
        for name,digest in hashes.items():
            if sha(z.read('BattleAtmosphere/'+name)) != digest:
                raise SystemExit('Archive content mismatch: '+name)
    if activation.read_bytes()!=activation_before:
        raise SystemExit('Activation file unexpectedly changed')
    receipt['archive']={'path':str(output),'sha256':sha(output.read_bytes()),'bytes':output.stat().st_size}
    (ROOT/'Development/release-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Packaged:',output)
    print('Runtime files:',len(hashes),'ZIP bytes:',output.stat().st_size)
    print('SHA256:',receipt['archive']['sha256'])
    print('Activated mods unchanged. Runtime battle behavior remains UNVERIFIED.')


if __name__=='__main__':
    main()
