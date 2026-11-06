import copy,json,unittest
from datetime import datetime
from cloud_reel import KST
from meta_followup import load_policy,validate_receipt

class FollowupSafety(unittest.TestCase):
    def setUp(self):
        self.p,self.d=load_policy()
        self.now=datetime.now(KST)
        self.r={'request_id':'issue-meta-123','policy_revision':'a'*40,'mode':'check','account':'issue.cards','design_id':self.p['design_id'],
          'published':False,'gmail_readonly_verified':True,'checked_at':self.now.isoformat(),'status':'waiting_reply'}
    def valid(self):validate_receipt(self.r,self.p,'a'*40,'issue-meta-123','check',self.now)
    def test_waiting_does_not_claim_clearance(self):self.valid();self.assertEqual(self.r['status'],'waiting_reply')
    def test_wrong_account(self):
        self.r['account']='other';self.assertRaises(RuntimeError,self.valid)
    def test_clearance_without_authenticated_evidence(self):
        self.r['status']='cleared_export_ready';self.assertRaises(RuntimeError,self.valid)
    def test_exact_approved_hashes_required(self):
        self.r.update(export_verified=True,page_sha256=['0'*64]*5,urls=['https://export.canva.com/a']*5)
        self.assertRaises(RuntimeError,self.valid)
    def test_untrusted_export(self):
        self.r.update(export_verified=True,page_sha256=self.p['page_sha256'],urls=['https://attacker.test/a']*5)
        self.assertRaises(RuntimeError,self.valid)
    def test_approved_copy_and_event_date(self):
        self.assertEqual(self.d['basis_date'],'2026-11-05');self.assertEqual(len(self.p['page_sha256']),5)

if __name__=='__main__':unittest.main()
