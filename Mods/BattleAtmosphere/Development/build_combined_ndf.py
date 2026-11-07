"""Run official compiler/cooker separately from installation, preserving evidence."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess,sys
DEV=Path(__file__).resolve().parent;MOD=DEV.parent;ROOT=MOD.parents[1]
def main():
    subprocess.run([sys.executable,str(DEV/'validate_combined_profile.py')],check=True)
    before={str(p.relative_to(MOD)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [MOD/'GameData/Gameplay/Skirmish/SkirmishMacros/SkirmishAttacks.ndf',MOD/'GameData/Gameplay/Skirmish/Strategies/VeryHardSkirmishStrategy.ndf']}
    commands=[[str(ROOT/'WARNO.exe'),'-headless','-nodialogbox','-nocrashrpt','-c','-','-generatemod','BattleAtmosphere','-rootdata','.',
               'CommonData:Clusters/Bootstrap/ClusterBootstrapGeneration.ndf'],
              [str(ROOT/'Tools/AssetCooker.exe'),'-e','ProgDir:/CoreCatalog.cat','-g','./Gen/','--common-data','./CommonData/','--game-data','./GameData/']]
    results=[]
    for i,cmd in enumerate(commands):
        print('START',Path(cmd[0]).name,flush=True)
        log=DEV/('combined-ndf-build-'+str(i)+'.log')
        with log.open('wb') as f:
            p=subprocess.run(cmd,cwd=MOD,stdout=f,stderr=subprocess.STDOUT,timeout=480)
        results.append(dict(command=cmd,returncode=p.returncode,log=log.name,log_sha256=hashlib.sha256(log.read_bytes()).hexdigest()))
        if p.returncode:raise RuntimeError(log.read_text(encoding='utf-8',errors='replace')[-5000:])
    from inspect_compiled import inspect
    binary=MOD/'Gen/NDF/GFX/Skirmish.ndfbin';data=inspect(binary)
    data['version']='combined-arms-preview.5'
    import os
    sys.path.insert(0,str(Path(os.environ['TEMP'])/'codex-warno-zstd'));import zstandard
    body=zstandard.ZstdDecompressor().decompress(binary.read_bytes()[44:],max_output_size=32*1024*1024)
    for name in ('Attack_Armor_BA','Attack_Armor_BA_Autogen','Pool_BA_Armor_Opportunity'):
        assert name.encode() in body,name
    for name,h in before.items():assert hashlib.sha256((MOD/name).read_bytes()).hexdigest()==h
    result=dict(status='official-build-and-packaging-checked-not-installed',time=datetime.now(timezone.utc).isoformat(),sources=before,commands=results,
        compiled=data,armor_exports=True,config_version=3,deck_format_version=1)
    (DEV/'combined-ndf-build.json').write_text(json.dumps(result,indent=2))
    print('PASS official generation, armor exports and preserved constants',flush=True)
if __name__=='__main__':main()
