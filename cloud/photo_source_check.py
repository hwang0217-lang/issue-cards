"""Read-only source-photo diagnostics; no credentials or Canva/Instagram calls."""
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlsplit
import requests
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    out=ROOT/'cloud-reports';out.mkdir(exist_ok=True);report=[]
    for ident,p in json.loads((ROOT/'cloud/photo-catalog.json').read_text(encoding='utf-8')).items():
        u=urlsplit(p['url'])
        if u.scheme!='https' or u.hostname!='images.pexels.com' or u.username or u.password or u.port:raise RuntimeError('Unexpected source host')
        r=requests.get(p['url'],timeout=45,allow_redirects=False);r.raise_for_status()
        if len(r.content)>12_000_000:raise RuntimeError('Source exceeds bounded photo size')
        im=Image.open(io.BytesIO(r.content));im.load();digest=hashlib.sha256(r.content).hexdigest()
        (out/f'source-photo-{ident}.jpg').write_bytes(r.content)
        row={'photo_id':ident,'sha256':digest,'expected_sha256':p['sha256'],'matches':digest==p['sha256'],'size':list(im.size),'pixel_sha256':hashlib.sha256(im.convert('RGB').tobytes()).hexdigest(),'content_type':r.headers.get('Content-Type'),'etag':r.headers.get('ETag')}
        report.append(row);print(json.dumps(row))
    (out/'source-photo-check.json').write_text(json.dumps({'published':False,'instagram_calls':0,'canva_calls':0,'sources':report},indent=2),encoding='utf-8')
