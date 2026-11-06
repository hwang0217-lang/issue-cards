import copy,json,unittest,tempfile,os
from pathlib import Path
from unittest.mock import patch,Mock
from datetime import datetime
from cloud_reel import KST
from meta_followup import load_policy,validate_receipt,draft_digest,main,reconcile_publish_error

TEMP_ROOT=Path(__file__).resolve().parents[1]/"cloud-evidence"/"test-temp"
TEMP_ROOT.mkdir(parents=True,exist_ok=True)

class FollowupSafety(unittest.TestCase):
    def setUp(self):
        self.p,self.d=load_policy()
        support_patch=patch('support_browser.check_support',return_value=None)
        self.support_mock=support_patch.start();self.addCleanup(support_patch.stop)
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
        self.r.update(export_verified=True,page_sha256=self.p['page_sha256'],original_approved_page_sha256=self.p['page_sha256'],exact_pixel_identity=self.p['page_pixel_identity'],urls=['https://attacker.test/a']*5)
        self.assertRaises(RuntimeError,self.valid)
    def test_even_one_changed_pixel_identity_rejected(self):
        pixels=copy.deepcopy(self.p['page_pixel_identity']);pixels[0]['pixel_sha256']='0'*64
        self.r.update(export_verified=True,page_sha256=self.p['page_sha256'],original_approved_page_sha256=self.p['page_sha256'],exact_pixel_identity=pixels,urls=['https://export.canva.com/a']*5)
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
            with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as d,patch.dict(os.environ,{'META_FOLLOWUP_MODE':mode,'GITHUB_RUN_ID':'123'}),patch('meta_followup.OUT',Path(d)),patch('meta_followup.PublicationState',return_value=state),patch('meta_followup.gateway',return_value=({'status':status,'decision':{'status':'waiting_reply'}},'123')),patch('meta_followup.graph') as graph,patch('meta_followup.run_carousel') as publish:
                main();graph.assert_not_called();publish.assert_not_called()
    def test_failed_publish_reconciles_success_with_get_only(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as d:
            p=Path(d);(p/'connection.json').write_text(json.dumps({'publication_status':'publishing','container_id':'parent','gateway_run_id':'7'}))
            live={'id':'new','timestamp':self.now.isoformat(),'caption':'approved','media_type':'CAROUSEL_ALBUM','permalink':'https://www.instagram.com/p/example/','children':{'data':[{'id':str(i)} for i in range(5)]}}
            state=Mock()
            with patch('meta_followup.OUT',p),patch('cloud_reel.OUT',p),patch('meta_followup.graph',side_effect=[{'status_code':'PUBLISHED'},{'data':[live]}]) as g:
                r=reconcile_publish_error({'caption':'approved','canva_design_id':'DAHaDQgjnYk','approved_assets_sha256':'digest'},state,{'old'},self.now)
                self.assertTrue(r['published']);self.assertTrue(all(c.args[0]=='GET' for c in g.call_args_list));self.assertEqual(state.put.call_count,2)
    def test_unpublished_container_cannot_be_success(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as d:
            p=Path(d);(p/'connection.json').write_text(json.dumps({'publication_status':'publishing','container_id':'parent'}))
            with patch('meta_followup.OUT',p),patch('meta_followup.graph',return_value={'status_code':'ERROR'}) as g:
                self.assertIsNone(reconcile_publish_error({},Mock(),set(),self.now));self.assertEqual(g.call_count,1)
    def test_ui_clearance_export_is_independent_of_gmail(self):
        self.support_mock.return_value={'status':'cleared','provider_text_sha256':'verified-provider-hash'}
        state=Mock();state.read.return_value=({},None)
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as d,patch.dict(os.environ,{'META_FOLLOWUP_MODE':'check','GITHUB_RUN_ID':'123'}),patch('meta_followup.OUT',Path(d)),patch('meta_followup.PublicationState',return_value=state),patch('meta_followup.gateway',return_value=({'status':'support_export_ready'},'7')) as gateway,patch('meta_followup.graph',return_value={'username':'issue.cards'}) as get,patch('meta_followup.publication_plan',side_effect=RuntimeError('quality gate stop')),patch('meta_followup.run_carousel') as publish:
            self.assertRaisesRegex(RuntimeError,'quality gate stop',main)
            self.assertEqual(gateway.call_args.args[4:6],('support-export','-support'));self.assertTrue(all(c.args[0]=='GET' for c in get.call_args_list));publish.assert_not_called()

if __name__=='__main__':unittest.main()
