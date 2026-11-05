"""Server-only Canva MP4 validation and official Instagram URL delivery.

Never logs Canva URLs or tokens and never uploads MP4s as Actions artifacts.
The delivery-check mode creates an unpublished container, never a public post.
"""
import hashlib
import base64
import io
import json
import os
import re
import subprocess
import time
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
import requests
import imageio_ffmpeg
from design_policy import load_plan, require_quality_review

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
OUT = ROOT / 'cloud-reports'
GATEWAY_REPO = 'hwang0217-lang/korea-firsttrip'
API = 'https://graph.instagram.com/v26.0'
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

def inspect_decoded_output(stderr):
    stderr=stderr.split('Output #',1)[0]
    size=re.search(r'Video:[^\n]*?\b(\d{2,5})x(\d{2,5})\b',stderr)
    length=re.search(r'Duration:\s*(\d+):(\d+):([0-9.]+)',stderr)
    if not size or not length:raise RuntimeError('Decoded MP4 metadata unavailable')
    duration=int(length[1])*3600+int(length[2])*60+float(length[3])
    return {'width':int(size[1]),'height':int(size[2]),'duration':duration,
            'audio_streams':len(re.findall(r'Stream #[^\n]*?: Audio:',stderr))}

def require_export_url(url):
    parsed = urlparse(url)
    if (parsed.scheme != 'https' or not parsed.hostname or
            not parsed.hostname.endswith('.canva.com') or parsed.username or parsed.password or
            parsed.port not in (None, 443)):
        raise RuntimeError('Untrusted Canva URL; stopped')
    return url

def enforce_publish(plan, digest, media, journals, now):
    day = now.astimezone(KST).date().isoformat()
    if (plan.get('purpose') != 'production' or plan.get('approved') is not True or plan.get('date') != day or
            plan.get('approved_assets_sha256' if plan.get('export_format') == 'jpg' else 'approved_video_sha256') != digest or
            plan.get('review', {}).get('all_scenes_readable') is not True):
        raise RuntimeError('Today hash-bound reviewed approval required')
    require_quality_review(plan, digest)
    for journal in journals:
        for key, row in journal.items():
            if key.startswith(day + '-') and row.get('status') in ('pending', 'published', 'published_verified', 'publish_unknown'):
                raise RuntimeError('Daily slot already attempted; no duplicate publication')
            if row.get('canva_design_id') == plan['canva_design_id'] and row.get('status') in ('published', 'published_verified'):
                raise RuntimeError('This Canva design was already published')
    for post in media:
        if not post.get('timestamp'):
            raise RuntimeError('Missing live timestamp')
        stamp = datetime.fromisoformat(post['timestamp'].replace('Z', '+00:00'))
        if stamp.astimezone(KST).date().isoformat() == day:
            raise RuntimeError('A live post already exists today')

class GitHub:
    def __init__(self, token): self.headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json'}
    def get(self, path):
        response = requests.get('https://api.github.com/' + path, headers=self.headers, timeout=45)
        if not response.ok: raise RuntimeError('GitHub connection HTTP ' + str(response.status_code))
        return response.json()
    def artifact(self, run_id, request_id):
        run = self.get(f'repos/{GATEWAY_REPO}/actions/runs/{run_id}')
        if (run.get('conclusion') != 'success' or run.get('path') != '.github/workflows/canva-export-gateway.yml'
                or run.get('display_title') != 'Canva export ' + request_id or run.get('head_branch') != 'main'):
            raise RuntimeError('Gateway execution identity or result mismatch')
        records = self.get(f'repos/{GATEWAY_REPO}/actions/runs/{run_id}/artifacts')['artifacts']
        candidates = [a for a in records if a['name'] == 'canva-export-' + request_id and not a['expired']]
        if len(candidates) != 1: raise RuntimeError('Expected one gateway receipt')
        response = requests.get(candidates[0]['archive_download_url'], headers=self.headers, timeout=45)
        if not response.ok: raise RuntimeError('Gateway receipt unavailable')
        with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
            names = bundle.namelist()
            if names != ['export.json']: raise RuntimeError('Unexpected gateway artifact')
            return json.loads(bundle.read('export.json'))
    def export_design(self, design_id):
        """One server trigger orchestrates the existing approved Canva gateway."""
        request_id='nordic-cloud-'+os.environ['GITHUB_RUN_ID']
        record={'request_id':request_id,'design_id':design_id,'status':'dispatching','published':False}
        state=PublicationState();path='cloud-reel-gateway-state.json'
        state.put(path,request_id,record,absent=True)
        response=requests.post('https://api.github.com/repos/'+GATEWAY_REPO+
            '/actions/workflows/canva-export-gateway.yml/dispatches',headers=self.headers,
            json={'ref':'main','inputs':{'design_id':design_id,'request_id':request_id,'registry_revision':os.environ['GITHUB_SHA']}},timeout=45)
        if response.status_code!=204:
            record.update(status='dispatch_rejected',http_status=response.status_code);state.put(path,request_id,record)
            raise RuntimeError('Canva gateway dispatch HTTP '+str(response.status_code)+'; do not repeat automatically')
        run_id=None
        for _ in range(80):
            if run_id is None:
                runs=self.get('repos/'+GATEWAY_REPO+'/actions/workflows/canva-export-gateway.yml/runs?event=workflow_dispatch&per_page=20')['workflow_runs']
                matches=[r for r in runs if r.get('display_title')=='Canva export '+request_id]
                if len(matches)>1:raise RuntimeError('Multiple gateway receipts require reconciliation')
                if matches:run_id=str(matches[0]['id']);record.update(gateway_run_id=run_id,status='running');state.put(path,request_id,record)
            else:
                run=self.get('repos/'+GATEWAY_REPO+'/actions/runs/'+run_id)
                if run['status']=='completed':
                    record['status']=run['conclusion'];state.put(path,request_id,record)
                    if run['conclusion']!='success':raise RuntimeError('Canva gateway did not complete successfully')
                    return run_id,request_id
            time.sleep(5)
        raise RuntimeError('Canva gateway pending; reconcile recorded run instead of redispatch')

class PublicationState:
    """CAS-protected state in this workflow's existing production repository."""
    def __init__(self):
        if os.environ.get('GITHUB_REPOSITORY') != 'hwang0217-lang/issue-cards':
            raise RuntimeError('Production state repository mismatch')
        self.base = 'https://api.github.com/repos/hwang0217-lang/issue-cards/contents/'
        self.headers = {'Authorization':'Bearer '+os.environ['GITHUB_TOKEN'], 'Accept':'application/vnd.github+json'}
    def read(self, path):
        r = requests.get(self.base+path, headers=self.headers, timeout=40)
        if r.status_code == 404: return {}, None
        if not r.ok: raise RuntimeError('Publication state read failed')
        item=r.json();return json.loads(base64.b64decode(item['content'])), item['sha']
    def put(self, path, key, entry, absent=False):
        rows, sha=self.read(path)
        if absent and key in rows: raise RuntimeError('Publication slot was already reserved')
        rows[key]=entry
        body={'message':'Record Nordic cloud delivery state','branch':'main',
              'content':base64.b64encode(json.dumps(rows,ensure_ascii=False,indent=2).encode()).decode()}
        if sha: body['sha']=sha
        r=requests.put(self.base+path,headers=self.headers,json=body,timeout=40)
        if not r.ok: raise RuntimeError('Publication state update failed; stop without retry')

def graph(method, path, body=None):
    response = requests.request(method, API + '/' + path,
        headers={'Authorization': 'Bearer ' + os.environ['IG_ACCESS_TOKEN']},
        data=body, timeout=60, allow_redirects=False)
    try: result = response.json()
    except ValueError: raise RuntimeError('Instagram non-JSON response; reconcile without retry')
    if not response.ok or result.get('error'):
        error = result.get('error', {})
        raise RuntimeError('Instagram HTTP %s / code %s / subcode %s' %
                           (response.status_code, error.get('code'), error.get('error_subcode')))
    return result

def save_report(report):
    OUT.mkdir(exist_ok=True)
    (OUT / 'connection.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

def run():
    mode = os.environ.get('CLOUD_REEL_MODE', 'export-check')
    if mode not in ('export-check', 'delivery-check', 'publish'): raise RuntimeError('Invalid mode')
    plan = load_plan(ROOT, os.environ.get('CLOUD_PLAN_PATH', ''), datetime.now(KST).date().isoformat())
    gateway=GitHub(os.environ['CANVA_GATEWAY_GH_TOKEN'])
    run_id = os.environ.get('CANVA_GATEWAY_RUN_ID',''); request_id = os.environ.get('CANVA_GATEWAY_REQUEST_ID','')
    if not run_id and not request_id and mode == 'publish':
        run_id = plan.get('export_receipt', {}).get('run_id', '')
        request_id = plan.get('export_receipt', {}).get('request_id', '')
        if not run_id or not request_id: raise RuntimeError('Publishing requires the exact reviewed export receipt')
    if not run_id and not request_id:
        run_id,request_id=gateway.export_design(plan['canva_design_id'])
    if not re.fullmatch(r'\d+', run_id) or not re.fullmatch(r'nordic-[a-z0-9-]{8,90}', request_id):
        raise RuntimeError('Invalid gateway receipt reference')
    result = gateway.artifact(run_id, request_id)
    if (result.get('status') != 'success' or result['designId'] != plan['canva_design_id'] or
            result['requestId'] != request_id or result.get('project') != 'issue' or result.get('purpose') != plan.get('purpose') or result.get('format') != plan.get('export_format', 'mp4') or not re.fullmatch(r'[0-9a-f]{40}', result.get('registryRevision', ''))):
        raise RuntimeError('Mismatched Canva export receipt')
    if datetime.fromisoformat(result['expiresAt'].replace('Z', '+00:00')) <= datetime.now(timezone.utc):
        raise RuntimeError('Canva export expired; no blind retry')
    if plan.get('export_format') == 'jpg':
        from cloud_carousel import run_carousel
        return run_carousel(mode, plan, result, run_id)
    if len(result.get('urls', [])) != 1: raise RuntimeError('Expected one MP4 URL')
    url = require_export_url(result['urls'][0])
    print('::add-mask::' + url)
    OUT.mkdir(exist_ok=True); video = OUT / 'server-only.mp4'
    response = requests.get(url, timeout=90, allow_redirects=False)
    if response.status_code != 200 or len(response.content) > 150_000_000:
        raise RuntimeError('Canva MP4 unavailable or exceeds bound')
    video.write_bytes(response.content)
    digest = hashlib.sha256(response.content).hexdigest()
    decoded=subprocess.run([FFMPEG,'-hide_banner','-i',str(video),'-f','null','-'],check=True,capture_output=True,text=True)
    visual=inspect_decoded_output(decoded.stderr)
    audio=visual['audio_streams'];duration=visual['duration']
    if abs(duration - plan['duration_seconds']) > .15 or (visual['width'], visual['height']) != (1080, 1920):
        raise RuntimeError('Video duration or dimensions changed')
    audio_peak = None
    if audio:
        levels=subprocess.run([FFMPEG,'-hide_banner','-i',str(video),'-vn','-af','volumedetect','-f','null','-'],
                              check=True,capture_output=True,text=True)
        match=re.search(r'max_volume:\s*(-?[0-9.]+) dB',levels.stderr)
        if not match: raise RuntimeError('Audio is silent or its level cannot be verified')
        audio_peak=float(match.group(1))
        if audio_peak < -50: raise RuntimeError('Audio level too low; stop before delivery')
    for index, second in enumerate(plan['scene_review_seconds'], 1):
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-ss', str(second), '-i', str(video), '-frames:v', '1',
                        '-vf', 'scale=390:-1', str(OUT / f'scene-{index:02d}.png')], check=True)
    report = {'mode': mode, 'design_id': plan['canva_design_id'], 'gateway_run_id': run_id, 'gateway_request_id': request_id,
        'registry_revision': result['registryRevision'], 'export_job_id': result['jobId'], 'design_updated_at': result.get('designUpdatedAt'),
        'video_sha256': digest, 'duration_seconds': duration, 'width':visual['width'], 'height':visual['height'],
        'audio_streams': audio, 'audio_peak_db':audio_peak, 'full_decode': True, 'pc_video_download': False,
        'scene_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.glob('scene-*.png'))},
        'published': False, 'unpublished_container_created': False}
    save_report(report)
    if mode == 'export-check': return
    if not audio or plan.get('music_embedded_in_canva') is not True:
        raise RuntimeError('Music must be included in the Canva export before delivery')
    identity = graph('GET', 'me?fields=id,username')
    if identity.get('username') != plan['account']: raise RuntimeError('Wrong Instagram identity')
    if os.environ.get('PUBLISH_PAUSED', '1') != '0': raise RuntimeError('Account publishing paused; no delivery')
    if mode == 'publish':
        posts = graph('GET', 'me/media?fields=id,permalink,timestamp&limit=15').get('data', [])
        journals = [PublicationState().read('' + name)[0] for name in ('managed-state.json', 'reels-state.json')]
        enforce_publish(plan, digest, posts, journals, datetime.now(KST))
    state=PublicationState();ledger='cloud-reel-delivery-state.json';key=mode+'-'+run_id
    records,_=state.read(ledger)
    if key in records:
        # A rerun must not create a second container after an ambiguous request.
        raise RuntimeError('Delivery already attempted; reconcile recorded container instead of repeating')
    report['container_status']='creating';save_report(report);state.put(ledger,key,report,absent=True)
    pubkey=datetime.now(KST).date().isoformat()+'-cloud'
    if mode=='publish':
        state.put('managed-state.json',pubkey,{'status':'pending','at':datetime.now(KST).isoformat(),
            'format':plan.get('format', 'reel'),'canva_design_id':plan['canva_design_id'],'sha256':digest},absent=True)
    # No automatic POST retry: one request creates the unpublished container.
    try:
        container=graph('POST',identity['id']+'/media',{'media_type':'REELS','video_url':url,
            'caption':plan['caption'],'share_to_feed':'true','thumb_offset':2000,'is_ai_generated':'true'})
    except Exception:
        report['container_status']='creation_unknown';save_report(report);state.put(ledger,key,report)
        raise
    report.update(container_id=container['id'], container_status='processing', unpublished_container_created=True)
    save_report(report);state.put(ledger,key,report)
    for _ in range(40):
        status = graph('GET', container['id'] + '?fields=status_code')['status_code']
        report['container_status'] = status;save_report(report)
        if status == 'FINISHED': break
        if status in ('ERROR', 'EXPIRED'): raise RuntimeError('Instagram container rejected')
        time.sleep(10)
    else: raise RuntimeError('Container still pending; reconcile this ID without retry')
    state.put(ledger,key,report)
    if mode == 'delivery-check': return
    # Publication requires a separately approved immutable hash and a free daily slot.
    report['publication_status']='publishing';save_report(report);state.put(ledger,key,report)
    try:
        published=graph('POST',identity['id']+'/media_publish',{'creation_id':container['id']})
    except Exception:
        report['publication_status']='publish_unknown';save_report(report);state.put(ledger,key,report)
        raise
    report['media_id']=published['id'];save_report(report);state.put(ledger,key,report)
    actual = graph('GET', published['id'] + '?fields=id,permalink,media_type,media_product_type,timestamp')
    if actual.get('media_product_type') != 'REELS' or not actual.get('permalink'):
        raise RuntimeError('Publication result requires reconciliation; never repeat')
    report.update(published=True, publication_status='published_verified', permalink=actual['permalink'])
    save_report(report);state.put(ledger,key,report)
    entry={'status':'published','at':actual['timestamp'],'format':plan.get('format', 'reel'),'account':'issue.cards',
        'canva_design_id':plan['canva_design_id'],'sha256':digest,'media_id':actual['id'],'permalink':actual['permalink']}
    state.put('managed-state.json',pubkey,entry)
    state.put('reels-state.json',pubkey,{**entry,'status':'published_verified'})

if __name__ == '__main__':
    try: run()
    except Exception as exc:
        # Prevent signed URLs and request internals from entering public Actions logs.
        message = str(exc)
        if 'https://' in message or 'http://' in message: message = 'Network operation failed; inspect saved stage, do not retry blindly'
        raise SystemExit(message)
