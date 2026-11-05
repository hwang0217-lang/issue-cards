"""Same-account renewal; seal directly into the same repository's Actions Secret."""
import os,base64
import requests
from nacl.public import PublicKey,SealedBox

REPO='hwang0217-lang/issue-cards'
def main():
    if os.environ.get('GITHUB_REPOSITORY')!=REPO:raise RuntimeError('Wrong renewal repository')
    writer=os.environ.get('IG_SECRET_WRITER_TOKEN')
    if not writer:raise RuntimeError('Dedicated same-repository renewal storage authorization missing')
    headers={'Authorization':'Bearer '+writer,'Accept':'application/vnd.github+json'}
    base='https://api.github.com/repos/'+REPO+'/actions/secrets/'
    # Verify durable storage authorization BEFORE refreshing the existing token.
    key=requests.get(base+'public-key',headers=headers,timeout=30,allow_redirects=False)
    if not key.ok:raise RuntimeError('Renewal storage authorization HTTP '+str(key.status_code))
    public=key.json();old=os.environ['IG_ACCESS_TOKEN']
    def identity(token):
        r=requests.get('https://graph.instagram.com/v26.0/me',params={'fields':'id,username'},headers={'Authorization':'Bearer '+token},timeout=30,allow_redirects=False)
        if not r.ok or r.json().get('username')!='issue.cards':raise RuntimeError('Issue identity not verified for renewal')
        return r.json()['id']
    before=identity(old)
    r=requests.get('https://graph.instagram.com/refresh_access_token',params={'grant_type':'ig_refresh_token','access_token':old},timeout=40,allow_redirects=False)
    data=r.json()
    if not r.ok or not data.get('access_token') or data.get('expires_in',0)<7*86400:raise RuntimeError('Instagram renewal unconfirmed; no secret update')
    new=data['access_token']
    if identity(new)!=before:raise RuntimeError('Renewed account mismatch')
    ciphertext=base64.b64encode(SealedBox(PublicKey(base64.b64decode(public['key']))).encrypt(new.encode())).decode()
    put=requests.put(base+'IG_ACCESS_TOKEN',headers=headers,json={'key_id':public['key_id'],'encrypted_value':ciphertext},timeout=30,allow_redirects=False)
    if put.status_code not in (201,204):raise RuntimeError('Renewal secret storage unconfirmed; no blind repeat')
    print('Same issue account renewed and sealed in original Actions Secret; expiry days='+str(data['expires_in']//86400))

if __name__=='__main__':
    try:main()
    except requests.RequestException:raise SystemExit('Renewal network failure; no token/URL disclosed, reconcile before retry')
