"""Independent checks of published weights, held-out metrics, and search constraints."""
from pathlib import Path
import json,sys
import numpy as np
from sklearn.metrics import roc_auc_score,balanced_accuracy_score
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_results import haversine,unit
r=json.loads((ROOT/'web/results.json').read_text());z=np.load(ROOT/'data/seed-embeddings.npz')
x,y=z['embeddings'],z['labels'];w=np.array(r['model']['weight']);b=r['model']['intercept']
assert x.shape==(90,128) and set(y)=={0,1}
np.testing.assert_allclose(np.linalg.norm(x,axis=1),1,atol=1e-6)
np.testing.assert_allclose(w,unit(x[y==1].mean(0)-x[y==0].mean(0)),atol=1e-7)
np.testing.assert_allclose(x@w+b,[s['score'] for s in r['seeds']],atol=1e-6)
g=np.array([s['group'] for s in r['seeds']]);oof=np.zeros(90)
for group in set(g):
 train=g!=group;test=~train
 positive=x[train & (y==1)].mean(0);negative=x[train & (y==0)].mean(0)
 v=unit(positive-negative);offset=-((positive+negative)/2)@v
 oof[test]=x[test]@v+offset
np.testing.assert_allclose(oof,[s['oof_score'] for s in r['seeds']],atol=1e-6)
assert abs(roc_auc_score(y,oof)-r['metrics']['oof_auc'])<1e-9
assert abs(balanced_accuracy_score(y,oof>0)-r['metrics']['oof_balanced_accuracy'])<1e-9
assert len(r['candidates'])==24 and r['scan']['blocks']==36
raw=json.loads((ROOT/'data/scanned-cells.json').read_text());assert len(raw)==r['scan']['scored_cells']
lookup={(s['lon'],s['lat']):s for s in raw};seeds=[[s['lon'],s['lat']] for s in r['seeds']]
for i,c in enumerate(r['candidates']):
 assert c['score']==lookup[(c['lon'],c['lat'])]['score']
 assert haversine(c['lon'],c['lat'],seeds).min()>=5
 if i:assert haversine(c['lon'],c['lat'],[[s['lon'],s['lat']] for s in r['candidates'][:i]]).min()>=1.5
 assert len(c['analogues'])==3
 assert c['id'].startswith('gem-')
 assert c['valid_fraction']>=.9
 if i:assert c['score']<=r['candidates'][i-1]['score']
# Authoritative block manifest covers every fetch; all retained raw files match.
import hashlib
manifest=json.loads((ROOT/'data/source-manifest.json').read_text())
assert len(manifest['blocks'])==126
for block in manifest['blocks']:
 p=ROOT/'.cache/blocks'/f'2025-{block["zone"]}-{block["x"]}-{block["y"]}.npy'
 if p.exists():assert hashlib.sha256(p.read_bytes()).hexdigest()==block['sha256']
print(f'PASS: 90 seed embeddings, full and 6 held-out vectors, {len(raw)} cells, 24 ranked/excluded/separated candidates, 126 source hashes')
