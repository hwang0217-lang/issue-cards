"""Runner-only temporary video transport, never a GitHub/media artifact."""
import hashlib
import os
import secrets
from urllib.parse import urlparse
import requests

def stage_video(file,row,persist):
    base=os.environ.get('ISSUE_MEDIA_BASE','')
    parsed=urlparse(base)
    if (parsed.scheme!='https' or parsed.hostname!='issue-media-delivery.apollo0217.workers.dev' or
        parsed.port or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment):
        raise RuntimeError('Temporary Nordic media endpoint missing or untrusted')
    key=os.environ.get('ISSUE_MEDIA_UPLOAD_KEY')
    if not key:raise RuntimeError('Temporary upload authorization missing')
    data=file.read_bytes()
    if not 0<len(data)<=32*1024*1024:raise RuntimeError('Temporary video size limit')
    digest=hashlib.sha256(data).hexdigest()
    url=base.rstrip('/')+'/media/'+secrets.token_hex(32)+'.mp4'
    print('::add-mask::'+url)
    row['transport_status']='staging';persist()
    reply=requests.put(url,data=data,headers={'Authorization':'Bearer '+key,'Content-Type':'video/mp4',
        'X-Content-SHA256':digest},timeout=180,allow_redirects=False)
    if not reply.ok:raise RuntimeError('Temporary video upload HTTP '+str(reply.status_code)+'; no retry')
    receipt=reply.json()
    if receipt.get('stored') is not True or receipt.get('sha256')!=digest or receipt.get('size')!=len(data):
        raise RuntimeError('Temporary video receipt mismatch')
    # Public fetch uses the same unlisted capability URL as Meta, no user login.
    check=requests.get(url,headers={'Range':'bytes=0-65535'},timeout=30,allow_redirects=False)
    if check.status_code!=206 or check.content!=data[:65536]:raise RuntimeError('Temporary range fetch mismatch')
    row.update(transport_status='ready',transport='temporary-cloudflare-url',
               transport_expires_ms=receipt['expires'],transport_sha256=digest);persist()
    return url
