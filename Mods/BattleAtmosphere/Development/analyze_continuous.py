"""Quantify actual positions in a native fixture receipt; no simulated output."""
from pathlib import Path
import sys,json,collections,math
sys.path.insert(0,str(Path(__file__).parent/'native_bridge'))
from verify_runtime import events

def analyze(path):
    r=json.loads(path.read_text()); out=r['stdout']
    frames=dict((a,(h,f)) for a,h,f in events(out,'SPACE_FRAME'))
    positions=events(out,'SPACE_POSITIONS');stat=events(out,'SPACE_STATUS')
    boards=events(out,'FRONT_STATUS'); result=[]; seen=set()
    for index,ps in enumerate(positions):
        tick=stat[index][0];board=dict((b[0],b) for b in boards[index][1])
        seen.update(u[0] for u in ps)
        for alliance in sorted(frames):
            own=[u for u in ps if u[1]==alliance and u[2]==6]
            if not own:continue
            home,f=frames[alliance]
            dl=[(((u[3]-home[0])*f[0]+(u[4]-home[1])*f[1])/215,
                 (-(u[3]-home[0])*f[1]+(u[4]-home[1])*f[0])/215) for u in own]
            ls=sorted(l for d,l in dl);front=board.get(alliance,[0,0,0,0])[3]
            band=collections.Counter(int(math.floor(l/260)) for d,l in dl if front-800<d<front+1000)
            gap=max((b-a-1 for a,b in zip(sorted(band),sorted(band)[1:])),default=0)
            result.append(dict(tick=tick,alliance=alliance,n=len(own),width80=round(ls[int(len(ls)*.9)]-ls[int(len(ls)*.1)],1),
              pairs120=sum(math.hypot(a[3]-b[3],a[4]-b[4])<120*215 for i,a in enumerate(own) for b in own[i+1:]),
              front=front,front_band_units=sum(band.values()),front_band_lanes=len(band),max_empty_internal_lanes=gap))
    return dict(receipt=path.name,returncode=r['returncode'],timeout=r['timeout'],stderr=r['stderr'],
         first=result[:2],last=result[-2:],max_sampled_planning_ms=max(v[-1] for v in stat),
         disappeared=len(seen-set(u[0] for u in positions[-1])),timeline=result,
         returns=dict(collections.Counter(v[1] for v in events(out,'SPACE_RETURN'))))

if __name__=='__main__':
    path=Path(__file__).parent/sys.argv[1];r=analyze(path)
    path.with_name(path.stem+'-metrics.json').write_text(json.dumps(r,indent=2))
    print(json.dumps({k:v for k,v in r.items() if k!='timeline'},indent=2))
