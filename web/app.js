'use strict';
(async()=>{
 const $=id=>document.getElementById(id);
 const response=await fetch('results.json');if(!response.ok)throw new Error('Could not load experiment results');
 const data=await response.json();let selected=data.candidates[0]?.id;
 const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const map=L.map('map',{scrollWheelZoom:false}).setView([38.3,-112.5],7);
 L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,attribution:'Imagery © Esri, Maxar, Earthstar Geographics, and the GIS User Community'}).addTo(map);
 L.control.scale({imperial:false}).addTo(map);
 const extentLayer=L.layerGroup().addTo(map);
 for(const b of data.scan.block_extents){L.rectangle([[b.south,b.west],[b.north,b.east]],{color:'#e3e7c9',weight:1,fillOpacity:0.02,dashArray:'3 4'}).bindTooltip(esc(b.region)+' · scanned block').addTo(extentLayer);}
 const candidateLayer=L.layerGroup().addTo(map),seedLayer=L.layerGroup();let markers=new Map();
 const coord=r=>`${r.lat.toFixed(4)}° N, ${Math.abs(r.lon).toFixed(4)}° W`;
 const preview=r=>{const dy=.012,dx=dy*2/Math.cos(r.lat*Math.PI/180);return 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?'+new URLSearchParams({bbox:[r.lon-dx,r.lat-dy,r.lon+dx,r.lat+dy].join(','),bboxSR:'4326',imageSR:'3857',size:'640,320',format:'jpg',f:'image'});};
 const rank=r=>data.candidates.findIndex(c=>c.id===r.id)+1;
 const icon=r=>L.divIcon({className:`pin${r.id===selected?' active':''}`,html:String(rank(r)).padStart(2,'0'),iconSize:[26,26],iconAnchor:[13,13]});
 const osm=r=>`https://www.openstreetmap.org/?mlat=${r.lat}&mlon=${r.lon}#map=15/${r.lat}/${r.lon}`;
 const google=r=>`https://www.google.com/maps/@?api=1&map_action=map&center=${r.lat},${r.lon}&zoom=15&basemap=satellite`;
 for(const r of data.scan.regions){const op=document.createElement('option');op.value=r.name;op.textContent=r.name;$('region').append(op);}
 for(const s of data.seeds){const marker=L.circleMarker([s.lat,s.lon],{radius:6,color:s.label?'#4b692d':'#57748c',fillColor:s.label?'#9caf70':'#a8bfce',weight:2,fillOpacity:.9});marker.bindPopup(`<b>${esc(s.name)}</b><br>${esc(s.category)}<br>Held-out score: ${s.oof_score.toFixed(3)}<br><a href="${esc(s.source)}" target="_blank" rel="noreferrer">Source ↗</a>`);marker.addTo(seedLayer);}
 const filtered=()=>data.candidates.filter(r=>$('region').value==='all'||r.region===$('region').value).sort((a,b)=>$('sort').value==='distance'?b.seed_distance_km-a.seed_distance_km:b.score-a.score);
 function showDetail(r,fly=false){
  selected=r.id;
  for(const c of data.candidates)if(markers.has(c.id))markers.get(c.id).setIcon(icon(c));
  for(const b of document.querySelectorAll('.card')){b.classList.toggle('selected',b.dataset.id===r.id);b.setAttribute('aria-pressed',String(b.dataset.id===r.id));}
  $('detail').innerHTML=`<img class="detail-photo" src="${preview(r)}" alt="Satellite view centered on candidate ${rank(r)} in ${esc(r.region)}"><div class="kicker">CANDIDATE ${String(rank(r)).padStart(2,'0')} / ${data.candidates.length}</div><h3 class="detail-name">${esc(r.name)}</h3><div class="coordinate">${coord(r)}</div><div class="detail-stats"><div><strong>${r.percentile.toFixed(1)}<small>th</small></strong>scan percentile</div><div><strong>${r.seed_distance_km.toFixed(1)} <small>km</small></strong>from nearest example</div></div><div class="analogue"><span>NEAREST SCENIC ANALOGUES</span>${r.analogues.slice(0,2).map(a=>`<a href="${esc(a.source)}" target="_blank" rel="noreferrer">${esc(a.name)}</a>`).join(' · ')}<br><small>Embedding similarity; not the same terrain.</small></div><div class="detail-actions"><a href="${google(r)}" target="_blank" rel="noreferrer">Satellite view ↗</a><a href="${osm(r)}" target="_blank" rel="noreferrer">Open map ↗</a></div>`;
  if(fly)map.flyTo([r.lat,r.lon],13,{duration:.8});
 }
 function render(fit=false){
  const rows=filtered();candidateLayer.clearLayers();markers=new Map();
  for(const r of rows){const m=L.marker([r.lat,r.lon],{icon:icon(r),title:r.name,keyboard:true}).on('click',()=>showDetail(r));m.addTo(candidateLayer);markers.set(r.id,m);}
  $('cards').innerHTML=rows.map(r=>`<button class="card${selected===r.id?' selected':''}" data-id="${r.id}" aria-pressed="${selected===r.id}"><div class="card-image"><img src="${preview(r)}" alt="Satellite view of ${esc(r.name)}" loading="lazy"><span class="rank">${String(rank(r)).padStart(2,'0')}</span></div><div class="card-content"><div class="kicker">${esc(r.region)}</div><h3>${coord(r)}</h3><div class="card-bottom"><b>${r.percentile.toFixed(1)}th percentile</b><span>${r.seed_distance_km.toFixed(0)} km from examples</span></div></div></button>`).join('');
  for(const b of document.querySelectorAll('.card'))b.onclick=()=>{showDetail(rows.find(r=>r.id===b.dataset.id),true);if(innerWidth<701)$('explore').scrollIntoView({behavior:'smooth'});};
  $('showing').textContent=`${rows.length} candidates · ranked by ${$('sort').value==='distance'?'distance from examples':'scenic-interest projection'}`;
  if(!rows.some(r=>r.id===selected))selected=rows[0]?.id;
  if(selected)showDetail(rows.find(r=>r.id===selected));else $('detail').innerHTML='<div class="kicker">SEARCH REGION</div><h3 class="detail-name">No top-24 candidates here.</h3><p class="sub">This region was scored with the same vector. Its cells did not enter the 24 highest-ranked, spatially separated picks.</p><p>Choose another region or explore the scanned blocks on the map.</p>';
  if(fit&&!rows.length){const blocks=data.scan.block_extents.filter(b=>b.region===$('region').value);if(blocks.length)map.fitBounds(L.latLngBounds(blocks.flatMap(b=>[[b.south,b.west],[b.north,b.east]])),{padding:[25,25]});}
  if(fit&&rows.length)map.fitBounds(L.latLngBounds(rows.map(r=>[r.lat,r.lon])),{padding:[45,45],maxZoom:11});
 }
 $('region').onchange=()=>render(true);$('sort').onchange=()=>render();$('seeds').onchange=()=>{$('seeds').checked?seedLayer.addTo(map):map.removeLayer(seedLayer);};
 $('area').textContent=data.scan.area_km2.toFixed(0);$('count').textContent=data.candidates.length;$('auc').textContent=data.metrics.oof_auc.toFixed(3);
 $('metric-note').textContent=`${(100*data.metrics.oof_balanced_accuracy).toFixed(1)}% held-out balanced accuracy. Seed bootstrap AUROC range: ${data.metrics.auc_seed_bootstrap_95.map(n=>n.toFixed(3)).join('–')}. ${data.scan.scored_cells.toLocaleString()} valid footprints scored.`;
 $('contrasts').innerHTML=Object.entries(data.metrics.contrasts).map(([name,m])=>`<div class="contrast"><span>Scenic vs ${name.includes('open')?'open land':'developed'}<small>${m.n} held-out examples</small></span><strong>${m.auc.toFixed(3)}<small>AUROC</small></strong></div>`).join('');
 $('folds').innerHTML=data.metrics.folds.map(f=>`<div class="fold"><div class="fold-label"><span>${esc(f.region.replaceAll('_',' '))} <small>· ${f.n} examples</small></span><span>${f.auc.toFixed(2)}</span></div><div class="bar"><i style="width:${100*f.auc}%"></i></div></div>`).join('');
 $('limitations').innerHTML=data.limitations.map(l=>`<li>${esc(l)}</li>`).join('');render(true);
 window.fieldnotes={data,map,filtered};
})().catch(e=>{document.getElementById('error').hidden=false;document.getElementById('error').textContent=`The experiment could not load: ${e.message}. Reload to try again.`;console.error(e);});
