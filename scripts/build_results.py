"""Read public OlmoEarth shards, fit a contrast direction, evaluate and scan.
No satellite imagery, names, coordinates or labels enter the 128-D scorer.
"""
from pathlib import Path
import concurrent.futures as cf
import hashlib
import json
import time
import numpy as np
import zarr
from obstore.store import S3Store
from pyproj import Transformer
from sklearn.metrics import roc_auc_score, balanced_accuracy_score

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache/blocks'
CACHE.mkdir(parents=True, exist_ok=True)
YEAR = 2025
DIMS = 128
SIZE = 256
POOL = 16 # 160m footprint, same for seeds and discovery
ORIGIN = 9502720
STORE_URL = 's3://olmoearth/olmoearth-v1-3-embeddings/embeddings.zarr'
ENDPOINT = 'https://data.source.coop'

def unit(x):
    return x / np.maximum(np.linalg.norm(x, axis=-1, keepdims=True), 1e-12)

def direction(x,y):
    return unit(x[y==1].mean(0)-x[y==0].mean(0))

def dequantize(q):
    r=q.astype(np.float32)/127.5
    return np.sign(r)*np.abs(r)**2

def corrected(q):
    """Match explorer parity-offset correction, locally per aligned 2.56km block."""
    valid=np.all(q!=-128,axis=0)
    v=dequantize(q)
    means=[]
    for dy in (0,1):
        for dx in (0,1):
            sub=v[:,dy::2,dx::2];ok=valid[dy::2,dx::2]
            means.append(sub[:,ok].mean(1) if ok.sum()>=32 else np.zeros(DIMS))
    means=np.array(means);offsets=means-means.mean(0)
    for k,(dy,dx) in enumerate([(0,0),(0,1),(1,0),(1,1)]):
        v[:,dy::2,dx::2]-=offsets[k,:,None,None]
    v[:,~valid]=0
    return v,valid

def pixel(lon,lat):
    zone=min(60,int((lon+180)//6)+1)
    e,n=Transformer.from_crs(4326,32600+zone,always_xy=True).transform(lon,lat)
    return zone,int(e//10),int((ORIGIN-n)//10)

def lonlat(zone,x,y):
    return Transformer.from_crs(32600+zone,4326,always_xy=True).transform(x*10,ORIGIN-y*10)

def haversine(lon,lat,other):
    # km, vectorized over other coordinates (longitude, latitude)
    a=np.radians(np.array(other));p=np.radians([lon,lat]);d=a-p
    h=np.sin(d[:,1]/2)**2+np.cos(p[1])*np.cos(a[:,1])*np.sin(d[:,0]/2)**2
    return 6371*2*np.arcsin(np.sqrt(np.clip(h,0,1)))

class Archive:
    def __init__(self):
        store=S3Store.from_url(STORE_URL,endpoint=ENDPOINT,skip_signature=True)
        self.root=zarr.open_group(zarr.storage.ObjectStore(store,read_only=True),mode='r')
        self.groups={}
    def block(self,key):
        zone,bx,by=key
        path=CACHE/f'{YEAR}-{zone}-{bx}-{by}.npy'
        if path.exists():return np.load(path)
        if zone not in self.groups:
            self.groups[zone]=self.root[f'utm{zone:02d}']
        g=self.groups[zone];years=np.asarray(g['time'][:]).astype(int)
        idx=np.flatnonzero(years==YEAR)
        if not len(idx):raise ValueError(f'{YEAR} unavailable in zone {zone}: {years}')
        for attempt in range(3):
            try:
                q=np.asarray(g['embeddings'][int(idx[0]),:DIMS,by:by+SIZE,bx:bx+SIZE])
                if q.shape!=(DIMS,SIZE,SIZE):raise ValueError(q.shape)
                np.save(path,q)
                return q
            except Exception:
                if attempt==2:raise
                time.sleep(attempt+1)

def main():
    start=time.time();a=Archive()
    seeds=json.loads((ROOT/'data/seeds.json').read_text())
    for s in seeds:
        z,x,y=pixel(s['lon'],s['lat']);s['pixel']=[z,x,y]
    keys=sorted({(z,x//SIZE*SIZE,y//SIZE*SIZE) for z,x,y in [s['pixel'] for s in seeds]})
    # Preselected search regions, no landscape labels used in candidate ranking.
    regions=[('San Rafael backcountry',-110.65,38.85),('Escalante country',-111.35,37.55),('Vermilion country',-111.90,36.90),('Basin and Range',-115.15,38.55)]
    search=[]
    for name,lon,lat in regions:
        z,x,y=pixel(lon,lat);bx=x//SIZE*SIZE;by=y//SIZE*SIZE
        for dx in (-1,0,1):
            for dy in (-1,0,1):search.append((name,(z,bx+dx*SIZE,by+dy*SIZE)))
    allkeys=sorted(set(keys+[k for _,k in search]))
    print(f'Fetching {len(allkeys)} blocks, {len(seeds)} seeds; year {YEAR}',flush=True)
    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(a.block,k):k for k in allkeys}
        for i,f in enumerate(cf.as_completed(futures)):
            q=f.result();print(f'block {i+1}/{len(allkeys)} {futures[f]} valid={(q[0]!=-128).mean():.3f}',flush=True)
    x=[]
    for s in seeds:
        z,px,py=s['pixel'];bx=px//SIZE*SIZE;by=py//SIZE*SIZE
        v,valid=corrected(a.block((z,bx,by)))
        # Snap to the exact same 160m grid used for discovery.
        ix=(px-bx)//POOL*POOL;iy=(py-by)//POOL*POOL
        ok=valid[iy:iy+POOL,ix:ix+POOL];s['valid_fraction']=float(ok.mean())
        if ok.mean()<.9:raise ValueError(f'Insufficient coverage for {s["name"]}')
        vec=unit(v[:,iy:iy+POOL,ix:ix+POOL][:,ok].mean(1))
        x.append(vec)
    x=np.array(x);y=np.array([s['label'] for s in seeds]);groups=np.array([s['group'] for s in seeds])
    w=direction(x,y);intercept=-float(((x[y==1].mean(0)+x[y==0].mean(0))/2)@w)
    oof=np.zeros(len(y));folds=[]
    for g in sorted(set(groups)):
        train=groups!=g;test=~train;wg=direction(x[train],y[train]);b=-float(((x[train & (y==1)].mean(0)+x[train & (y==0)].mean(0))/2)@wg)
        oof[test]=x[test]@wg+b
        folds.append(dict(region=g,n=int(test.sum()),auc=float(roc_auc_score(y[test],oof[test])),balanced_accuracy=float(balanced_accuracy_score(y[test],oof[test]>0))))
    rng=np.random.default_rng(42);aucs=[]
    for _ in range(2000):
        ix=rng.integers(0,len(y),len(y))
        if len(set(y[ix]))==2:aucs.append(roc_auc_score(y[ix],oof[ix]))
    metrics=dict(oof_auc=float(roc_auc_score(y,oof)),oof_balanced_accuracy=float(balanced_accuracy_score(y,oof>0)),auc_seed_bootstrap_95=np.quantile(aucs,[.025,.975]).tolist(),folds=folds,validation='Leave one geographic group out; all labels in each group held out. Bootstrap is by seed, not a population confidence interval.')
    metrics['contrasts']={}
    for category in ['ordinary developed control','ordinary open-land control']:
        mask=np.array([s['label']==1 or s['category']==category for s in seeds])
        metrics['contrasts'][category]=dict(n=int(mask.sum()),auc=float(roc_auc_score(y[mask],oof[mask])),balanced_accuracy=float(balanced_accuracy_score(y[mask],oof[mask]>0)))
    for i,s in enumerate(seeds):s.update(score=float(x[i]@w+intercept),oof_score=float(oof[i]))
    raw=[];valid_pixels=0
    coords=[[s['lon'],s['lat']] for s in seeds]
    for name,key in search:
        z,bx,by=key;v,valid=corrected(a.block(key));valid_pixels+=int(valid.sum())
        for iy in range(0,SIZE,POOL):
            for ix in range(0,SIZE,POOL):
                ok=valid[iy:iy+POOL,ix:ix+POOL]
                if ok.mean()<.9:continue
                vec=unit(v[:,iy:iy+POOL,ix:ix+POOL][:,ok].mean(1));score=float(vec@w+intercept)
                lon,lat=lonlat(z,bx+ix+POOL/2,by+iy+POOL/2)
                distance=float(haversine(lon,lat,coords).min())
                raw.append(dict(region=name,lon=lon,lat=lat,score=score,seed_distance_km=distance,valid_fraction=float(ok.mean()),vector=vec.tolist()))
    raw.sort(key=lambda r:r['score'],reverse=True)
    for i,r in enumerate(raw):r['percentile']=round(100*(len(raw)-i)/len(raw),2)
    picked=[]
    # Distance exclusion and nonmaximum suppression; same scorer for every cell.
    for r in raw:
        if r['seed_distance_km']<5:continue
        if picked and haversine(r['lon'],r['lat'],[[p['lon'],p['lat']] for p in picked]).min()<1.5:continue
        r=dict(r);vec=np.array(r.pop('vector'));similar=x[y==1]@vec;near=np.argsort(similar)[-3:][::-1];pos=[s for s in seeds if s['label']==1]
        r['analogues']=[dict(name=pos[j]['name'],cosine=float(similar[j]),source=pos[j]['source']) for j in near]
        r['id']=f'gem-{len(picked)+1:02d}';r['name']=f'{r["region"]} · {sum(p["region"]==r["region"] for p in picked)+1:02d}'
        picked.append(r)
        if len(picked)==24:break
    model=dict(dimensions=DIMS,year=YEAR,weight=w.tolist(),intercept=intercept,formula='unit(mean(unit(scenic)) - mean(unit(ordinary))); score = unit(pooled_embedding) dot weight + intercept',pool_m=160,parity_correction='Per 256x256 block, subtract the four parity means relative to their grand mean before pooling.',source=STORE_URL,endpoint=ENDPOINT)
    results=dict(title='Earth, off the shortlist',generated_at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),model=model,metrics=metrics,seeds=seeds,candidates=picked,scan=dict(regions=[dict(name=n,lon=lon,lat=lat) for n,lon,lat in regions],block_extents=[dict(region=n,west=lonlat(k[0],k[1],k[2]+SIZE)[0],south=lonlat(k[0],k[1],k[2]+SIZE)[1],east=lonlat(k[0],k[1]+SIZE,k[2])[0],north=lonlat(k[0],k[1]+SIZE,k[2])[1]) for n,k in search],blocks=len(search),area_km2=len(search)*(SIZE*.01)**2,valid_pixels=valid_pixels,scored_cells=len(raw),pool_m=160,seed_exclusion_km=5,min_separation_km=1.5),limitations=['Subjective, hand-curated labels; 30 landmarks, 30 developed controls and 30 ordinary open-land controls are a small convenience sample.','Labels can reflect land cover, region and water rather than aesthetic quality. Separate scenic-versus-open-land held-out metrics are reported; no human candidate preference study.','Candidates are unlabelled grid cells, not verified destinations. Hidden means at least 5 km from all training examples, not low visitor counts.','No access, ownership, safety, trail, ecological sensitivity or popularity assessment. Satellite imagery on the site can be newer than 2025 embeddings.','Four deliberately chosen western-US search regions; no global coverage claim. 160 m pooled footprints cannot resolve a viewpoint or trail.'])
    (ROOT/'web/results.json').write_text(json.dumps(results,indent=2)+'\n')
    (ROOT/'data/interestingness-vector.json').write_text(json.dumps(model,indent=2)+'\n')
    np.savez_compressed(ROOT/'data/seed-embeddings.npz',embeddings=x,labels=y,ids=np.array([s['id'] for s in seeds]))
    # Preserve all candidate cell scores for independent ranking and coverage checks.
    for r in raw:r.pop('vector')
    (ROOT/'data/scanned-cells.json').write_text(json.dumps(raw,separators=(',',':'))+'\n')
    manifest=dict(year=YEAR,source=STORE_URL,blocks=[dict(zone=k[0],x=k[1],y=k[2],sha256=hashlib.sha256((CACHE/f'{YEAR}-{k[0]}-{k[1]}-{k[2]}.npy').read_bytes()).hexdigest()) for k in allkeys])
    (ROOT/'data/source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(metrics,indent=2),flush=True);print(f'Wrote {len(picked)} candidates from {len(raw)} cells in {time.time()-start:.1f}s',flush=True)

if __name__=='__main__':main()
