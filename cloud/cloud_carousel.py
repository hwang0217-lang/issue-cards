"""Server-only Canva JPEG pages → official Instagram carousel containers.

All POSTs are single attempts; durable 'creating' records block ambiguous reruns.
No signed media URLs are written to public state or output artifacts.
"""
import hashlib
import io
import json
import time
from datetime import datetime
from PIL import Image
from cloud_reel import OUT, KST, PublicationState, enforce_publish, graph, require_export_url, save_report
import requests

def image_bytes(url):
    require_export_url(url)
    r = requests.get(url, timeout=60, allow_redirects=False)
    if r.status_code != 200 or len(r.content) > 8_000_000:
        raise RuntimeError('Carousel JPEG missing or exceeds Instagram image bound')
    image = Image.open(io.BytesIO(r.content))
    if image.format != 'JPEG' or image.size != (1080, 1350):
        raise RuntimeError('Expected original 1080x1350 JPEG page')
    image.load()
    return r.content, image

def assets_digest(hashes):
    return hashlib.sha256(json.dumps(hashes, separators=(',', ':')).encode()).hexdigest()

def wait_finished(container_id):
    for _ in range(40):
        status = graph('GET', container_id + '?fields=status_code')['status_code']
        if status == 'FINISHED': return status
        if status in ('ERROR', 'EXPIRED'):
            raise RuntimeError('Carousel container rejected; reconcile existing ID')
        time.sleep(5)
    raise RuntimeError('Carousel container still processing; no blind recreation')

def run_carousel(mode, plan, result, run_id):
    if len(result.get('urls', [])) != plan['page_count']:
        raise RuntimeError('Carousel export page count mismatch')
    OUT.mkdir(exist_ok=True)
    hashes = []
    for index, url in enumerate(result['urls'], 1):
        data, image = image_bytes(url)
        hashes.append(hashlib.sha256(data).hexdigest())
        image.resize((390, 488), Image.Resampling.LANCZOS).save(OUT / f'page-{index:02d}.png')
    digest = assets_digest(hashes)
    report = {'mode': mode, 'format': 'carousel', 'design_id': plan['canva_design_id'],
              'gateway_run_id': run_id, 'gateway_request_id': result.get('requestId'), 'registry_revision': result['registryRevision'],
              'design_updated_at': result.get('designUpdatedAt'), 'page_count': len(hashes),
              'width': 1080, 'height': 1350, 'page_sha256': hashes, 'assets_sha256': digest,
              'pc_media_download': False, 'published': False, 'unpublished_container_created': False}
    save_report(report)
    if mode == 'export-check': return
    identity = graph('GET', 'me?fields=id,username')
    if identity.get('username') != plan['account']: raise RuntimeError('Wrong Instagram identity')
    import os
    if os.environ.get('PUBLISH_PAUSED', '1') != '0': raise RuntimeError('Account publishing paused')
    state = PublicationState()
    if mode == 'publish':
        posts = graph('GET', 'me/media?fields=id,permalink,timestamp&limit=15').get('data', [])
        journals = [state.read('' + n)[0] for n in ('managed-state.json', 'reels-state.json')]
        enforce_publish(plan, digest, posts, journals, datetime.now(KST))
    ledger = 'cloud-reel-delivery-state.json'
    key = mode + '-' + run_id
    report.update(container_status='creating', child_container_ids=[])
    state.put(ledger, key, report, absent=True)
    pubkey = datetime.now(KST).date().isoformat() + '-cloud'
    if mode == 'publish':
        state.put('managed-state.json', pubkey, {'status': 'pending',
                  'at': datetime.now(KST).isoformat(), 'format': 'carousel',
                  'canva_design_id': plan['canva_design_id'], 'sha256': digest}, absent=True)
    # Record before every mutating request. Never automatically retry a failed POST.
    for index, url in enumerate(result['urls'], 1):
        report.update(container_status='creating_child', creating_page=index)
        save_report(report); state.put(ledger, key, report)
        child = graph('POST', identity['id'] + '/media', {'image_url': url, 'is_carousel_item': 'true'})
        report['child_container_ids'].append(child['id'])
        save_report(report); state.put(ledger, key, report)
        wait_finished(child['id'])
    report['container_status'] = 'creating_parent'
    save_report(report); state.put(ledger, key, report)
    parent = graph('POST', identity['id'] + '/media', {'media_type': 'CAROUSEL',
                   'children': ','.join(report['child_container_ids']), 'caption': plan['caption'],
                   'is_ai_generated': str(plan.get('is_ai_generated', True)).lower()})
    report.update(container_id=parent['id'], unpublished_container_created=True, container_status='processing')
    save_report(report); state.put(ledger, key, report)
    report['container_status'] = wait_finished(parent['id'])
    save_report(report); state.put(ledger, key, report)
    if mode == 'delivery-check': return
    report['publication_status'] = 'publishing'
    save_report(report); state.put(ledger, key, report)
    published = graph('POST', identity['id'] + '/media_publish', {'creation_id': parent['id']})
    report['media_id'] = published['id']
    save_report(report); state.put(ledger, key, report)
    actual = graph('GET', published['id'] + '?fields=id,permalink,media_type,timestamp')
    if actual.get('media_type') != 'CAROUSEL_ALBUM' or not actual.get('permalink'):
        raise RuntimeError('Carousel publication needs reconciliation; never retry')
    report.update(published=True, publication_status='published_verified', permalink=actual['permalink'])
    save_report(report); state.put(ledger, key, report)
    entry = {'status': 'published', 'at': actual['timestamp'], 'format': 'carousel',
             'account': 'issue.cards', 'canva_design_id': plan['canva_design_id'],
             'sha256': digest, 'media_id': actual['id'], 'permalink': actual['permalink']}
    state.put('managed-state.json', pubkey, entry)
