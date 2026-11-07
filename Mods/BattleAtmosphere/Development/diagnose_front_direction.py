"""Reconstruct recorded first routes; independent of new controller metrics."""
import ast,collections,json,math,re
from pathlib import Path
DEV=Path(__file__).resolve().parent
source=DEV/'runtime-live-preview5-38916-20261107T011345Z.log'
def events(name):
    return [ast.literal_eval(re.sub(r'(?<=\d)L\b','',s.split(name+' ',1)[1]))
            for s in source.read_text().splitlines() if s.startswith('BA_RUNTIME '+name+' ')]
frames={a:(h,f) for a,h,f in events('SPACE_FRAME')}
routes={};observed=[]
for r in events('SPACE_ROUTE'):routes.setdefault(r[0],r)
seen=set()
for uid,x,y,accepted in events('SPACE_ORDER'):
    if uid in seen or uid not in routes:continue
    seen.add(uid);r=routes[uid]
    def origin(a):
        h,f=frames[a];d,l=r[5:6]+r[7:8]
        return h[0]+215*(d*f[0]-l*f[1]),h[1]+215*(d*f[1]+l*f[0])
    alliance=min(frames,key=lambda a:math.dist(origin(a),(x,y)))
    p=origin(alliance);h,f=frames[alliance]
    span=math.dist(h,frames[1-alliance][0])/215
    # Early spawns cluster near the OTHER deployment. Use their closest
    # physical deployment to establish an independent home-to-opponent axis.
    side=min(frames,key=lambda a:math.dist(p,frames[a][0]))
    real_f=frames[side][1]
    gain=((x-p[0])*real_f[0]+(y-p[1])*real_f[1])/215
    observed.append(dict(uid=uid,alliance=alliance,physical_side=side,position=p,
                         target=[x,y],logged_start_depth=r[5],map_span=span,actual_first_leg_forward_m=gain))
    if len(observed)>=48:break
result=dict(source=source.name,evidence='First recorded origins reconstructed from SPACE_ROUTE and matched to SPACE_ORDER; nearest physical deployment is inferred, not a live-memory owner read.',
            first_routes=len(observed),side_mapping=dict(collections.Counter('%s->%s'%(r['alliance'],r['physical_side']) for r in observed)),
            backwards_first_legs=sum(r['actual_first_leg_forward_m']<0 for r in observed),rows=observed)
(DEV/'direction-regression-evidence.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
