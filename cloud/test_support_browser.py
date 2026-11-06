import hashlib,hmac,json,unittest
from datetime import datetime
from cloud_reel import KST
from support_browser import verify_receipt

class SupportProof(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(KST);self.key='example-key';self.data={'source':'instagram_support_inbox','account':'issue.cards','request_id':'issue-support-123','build_id':'reviewed','read_only':True,'published':False,'checked_at':self.now.isoformat(),'status':'cleared','owner_verified':True,'provider_label':'Instagram의 답변','url':'https://www.instagram.com/settings/help/','clearance_quote':'approved provider reply'}
        self.data['provider_text_sha256']=hashlib.sha256(self.data['clearance_quote'].encode()).hexdigest()
    def call(self,bad_signature=False):
        raw=json.dumps(self.data).encode();sig=hmac.new(self.key.encode(),raw,hashlib.sha256).hexdigest()
        return verify_receipt(raw,'bad' if bad_signature else sig,self.key,'issue-support-123','reviewed',self.now)
    def test_signed_owner_provider_proof(self):self.assertEqual(self.call()['status'],'cleared')
    def test_forged_signature_rejected(self):self.assertRaises(RuntimeError,self.call,True)
    def test_other_owner_rejected(self):self.data['account']='other';self.assertRaises(RuntimeError,self.call)
    def test_different_build_rejected(self):self.data['build_id']='unknown';self.assertRaises(RuntimeError,self.call)
    def test_reply_text_changed_rejected(self):self.data['clearance_quote']='changed';self.assertRaises(RuntimeError,self.call)
    def test_user_report_label_rejected(self):self.data['provider_label']='신고한 내용';self.assertRaises(RuntimeError,self.call)

if __name__=='__main__':unittest.main()
