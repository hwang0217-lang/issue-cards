import copy,json,unittest,tempfile,os
from pathlib import Path
from unittest.mock import patch,Mock
from datetime import datetime
from cloud_reel import KST
from meta_followup import load_policy,validate_receipt,draft_digest,main

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
    def test_only_serialization_whitespace_is_canonicalized(self):
        text=json.dumps(self.d,ensure_ascii=False,indent=2)
        self.assertEqual(draft_digest(json.loads(text.replace('\n','\r\n'))),draft_digest(self.d))
        changed=copy.deepcopy(self.d);changed['caption']+='x';self.assertNotEqual(draft_digest(changed),draft_digest(self.d))
    def test_waiting_and_export_check_never_use_instagram(self):
        for mode,status in [('check','waiting_reply'),('check','needs_review'),('export-check','export_check_pass')]:
            state=Mock();state.read.return_value=({},None)
            with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'META_FOLLOWUP_MODE':mode,'GITHUB_RUN_ID':'123'}),patch('meta_followup.OUT',Path(d)),patch('meta_followup.PublicationState',return_value=state),patch('meta_followup.gateway',return_value=({'status':status,'decision':{'status':'waiting_reply'}},'123')),patch('meta_followup.graph') as graph,patch('meta_followup.run_carousel') as publish:
                main();graph.assert_not_called();publish.assert_not_called()

if __name__=='__main__':unittest.main()
