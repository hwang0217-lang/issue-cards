"""Consume signed fixed-source provider UI evidence, never normal UI reassurance."""
import hashlib,hmac,json,os
from datetime import datetime,timedelta
import requests

URL='https://issue-support-reader.apollo0217.workers.dev'
LABELS={'Instagram의 답변','Instagram의 검토 결과','지원팀의 답변','검토 결과','Response from Instagram','Instagram response','Our response'}

def verify_receipt(raw,signature,key,request_id,build_id,now):
    expected=hmac.new(key.encode(),raw,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature or '',expected):raise RuntimeError('Invalid support-reader signature')
    data=json.loads(raw)
    if (data.get('source')!='instagram_support_inbox' or data.get('account')!='issue.cards' or data.get('request_id')!=request_id
        or data.get('build_id')!=build_id or data.get('read_only') is not True or data.get('published') is not False):
        raise RuntimeError('Wrong support source/owner/request/build')
    at=datetime.fromisoformat(data['checked_at'].replace('Z','+00:00'))
    if not timedelta(0)<=now-at<=timedelta(minutes=2):raise RuntimeError('Stale support evidence')
    if data.get('status')=='cleared':
        if (data.get('owner_verified') is not True or data.get('provider_label') not in LABELS or
            not data.get('url','').startswith('https://www.instagram.com/settings/help/') or not data.get('clearance_quote')
            or hashlib.sha256(data['clearance_quote'].encode()).hexdigest()!=data.get('provider_text_sha256')):
            raise RuntimeError('Missing exact provider-response evidence')
    return data

def check_support(policy,now):
    config=policy.get('support_browser',{})
    if config.get('enabled') is not True:return None
    key=os.environ.get('IG_SUPPORT_READ_KEY')
    if not key:raise RuntimeError('Support reader server authentication missing')
    request_id='issue-support-'+os.environ['GITHUB_RUN_ID']
    r=requests.post(URL+'/check',headers={'Authorization':'Bearer '+key,'User-Agent':'Mozilla/5.0 (compatible; IssueCardsSupportMonitor/1.0; +https://github.com/hwang0217-lang/issue-cards)'},json={'request_id':request_id},timeout=55,allow_redirects=False)
    if not r.ok:raise RuntimeError('Support browser stopped; inspect owner authentication or free-budget state')
    data=r.json()
    if data.get('status')=='auth_required':return {'status':'auth_required','reason':'one_time_cloud_login_required'}
    return verify_receipt(r.content,r.headers.get('X-Receipt-Signature'),key,request_id,config['build_id'],datetime.now(now.tzinfo))
