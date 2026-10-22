"""End-to-end UI checks against a local or tunneled copy; screenshots stay local."""
from pathlib import Path
import sys,json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
url=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8768'
output=ROOT/'.runtime';output.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(url,wait_until='networkidle',timeout=90000)
    page.wait_for_function('window.fieldnotes && document.querySelectorAll(".card").length === 24',timeout=30000)
    assert page.locator('#error').is_hidden()
    assert page.locator('.leaflet-marker-icon.pin').count()==24
    assert page.locator('.fold').count()==6
    assert page.locator('.contrast').count()==2
    assert page.locator('#count').inner_text()=='24'
    assert page.locator('.stats').inner_text().find('90')>=0
    # Click a different candidate and verify the detail panel tracks its rank.
    page.locator('.card').nth(3).click();assert 'CANDIDATE 04' in page.locator('#detail').inner_text()
    page.select_option('#sort','distance')
    distances=page.evaluate('window.fieldnotes.filtered().map(r=>r.seed_distance_km)')
    assert distances==sorted(distances,reverse=True)
    for name in page.evaluate('window.fieldnotes.data.scan.regions.map(r=>r.name)'):
        page.select_option('#region',name)
        count=page.locator('.card').count()
        assert count==page.evaluate('window.fieldnotes.filtered().length')
        if count==0:assert 'No top-24 candidates' in page.locator('#detail').inner_text()
    page.select_option('#region','all');page.select_option('#sort','score')
    page.check('#seeds');assert page.locator('.leaflet-interactive').count()>=90
    page.uncheck('#seeds')
    # Open downloaded data and license paths through the same public origin.
    for path in ['results.json','data/interestingness-vector.json','data/seeds.json','data/OLMOEARTH-LICENSE.txt','assets/LEAFLET-LICENSE.txt']:
        response=page.request.get(url.rstrip('/')+'/'+path);assert response.status==200,(path,response.status)
    page.locator('.card').first.click();page.evaluate('window.scrollTo(0,0)');page.wait_for_timeout(1500)
    page.screenshot(path=str(output/'desktop.png'),full_page=True)
    # Check actual map tile and remote satellite-preview decoding, not just DOM.
    page.locator('#explore').scroll_into_view_if_needed();page.wait_for_timeout(1500)
    images=page.evaluate('Array.from(document.querySelectorAll("#detail img, .leaflet-tile-loaded")).map(i=>({src:i.src,ok:i.complete && i.naturalWidth>0}))')
    assert images and all(i['ok'] for i in images),images
    page.set_viewport_size({'width':390,'height':844});page.evaluate('window.fieldnotes.map.invalidateSize();window.scrollTo(0,0)');page.wait_for_timeout(500)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'mobile horizontal overflow'
    page.screenshot(path=str(output/'mobile.png'),full_page=True)
    assert not errors,errors
    print(json.dumps({'url':url,'cards':24,'held_out_groups':6,'mobile_width':390,'decoded_images':len(images),'javascript_errors':errors,'result':'PASS'}))
    browser.close()
