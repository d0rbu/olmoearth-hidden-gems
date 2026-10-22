"""Cache Esri export previews with exact geographic extents and attribution."""
from pathlib import Path
import concurrent.futures as cf
import json, math, requests
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
URL='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export'
def fetch(r):
    # Geographic bbox adjusted to approximate a 2:1 aspect ratio on the ground.
    dy=.012;dx=dy*2/math.cos(math.radians(r['lat']))
    bbox=[r['lon']-dx,r['lat']-dy,r['lon']+dx,r['lat']+dy]
    params=dict(bbox=','.join(map(str,bbox)),bboxSR=4326,imageSR=3857,size='640,320',format='jpg',f='image')
    p=ROOT/'web/assets'/f'{r["id"]}.jpg'
    if True: # Refresh because a new fitted vector may select new coordinates for this ID.
        res=requests.get(URL,params=params,timeout=90);res.raise_for_status();p.write_bytes(res.content)
    with Image.open(p) as im:
        if im.size!=(640,320):raise ValueError((p,im.size))
    return dict(id=r['id'],bbox=bbox,url=requests.Request('GET',URL,params=params).prepare().url,attribution='Esri World Imagery; Esri, Maxar, Earthstar Geographics, and the GIS User Community. Imagery dates vary; not the 2025 model input.')
if __name__=='__main__':
    data=json.loads((ROOT/'web/results.json').read_text())
    with cf.ThreadPoolExecutor(max_workers=4) as pool:records=list(pool.map(fetch,data['candidates']))
    (ROOT/'data/preview-provenance.json').write_text(json.dumps(records,indent=2)+'\n')
    print(f'Validated {len(records)} satellite previews')
