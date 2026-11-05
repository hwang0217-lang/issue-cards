"""Read-only diagnosis. Quota availability never proves an action block is lifted."""
import json,os
from pathlib import Path
import requests

def main():
    output={'publication_attempted':False,'pause':os.environ.get('PUBLISH_PAUSED','1'),'checks':{}}
    def get(path,params=None):
        r=requests.get('https://graph.instagram.com/v26.0/'+path,params=params,
            headers={'Authorization':'Bearer '+os.environ['IG_ACCESS_TOKEN']},timeout=40,allow_redirects=False)
        data=r.json()
        if not r.ok:
            e=data.get('error',{});return {'ok':False,'http':r.status_code,'code':e.get('code'),'subcode':e.get('error_subcode')}
        return {'ok':True,'data':data}
    identity=get('me',{'fields':'id,username'})
    if not identity.get('ok') or identity['data'].get('username')!='issue.cards':
        output['checks']['identity']={'verified':False,'error':{k:v for k,v in identity.items() if k!='data'}}
    else:
        output['checks']['identity']={'verified':True,'username':'issue.cards'}
        quota=get(identity['data']['id']+'/content_publishing_limit',{'fields':'config,quota_usage'})
        output['checks']['publishing_quota']=quota
        posts=get('me/media',{'fields':'id,permalink,timestamp,media_type,caption','limit':9})
        output['checks']['recent_posts']=posts
    gh=requests.get('https://api.github.com/repos/hwang0217-lang/korea-firsttrip/actions/workflows/nordic-canva-produce.yml',
        headers={'Authorization':'Bearer '+os.environ.get('CANVA_GATEWAY_GH_TOKEN','')},timeout=40,allow_redirects=False)
    output['checks']['canva_gateway_http']=gh.status_code
    output['action_block_lifted']='unconfirmed: no supported read-only action-block clearance field'
    Path('cloud-reports').mkdir(exist_ok=True)
    Path('cloud-reports/preflight.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in output.items() if k!='checks'},ensure_ascii=False))
    if not output['checks']['identity']['verified']:raise RuntimeError('Issue account authentication needs repair')

if __name__=='__main__':main()
