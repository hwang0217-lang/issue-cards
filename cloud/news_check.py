import json
from pathlib import Path
from datetime import datetime
from cloud_reel import KST
from news_research import create_news_draft

if __name__=='__main__':
    out=Path('cloud-reports');out.mkdir(exist_ok=True)
    try:
        draft,usage,evidence=create_news_draft('Create five premium original Korean social-news Canva pages, proper Korean typography, different cover/comparison/timeline/summary compositions.','carousel',datetime.now(KST).date().isoformat(),[])
        result={'stage':'source_fact_check_passed','published':False,'draft':draft,'evidence':evidence,'usage':usage}
    except Exception as exc:
        result={'stage':'blocked','published':False,'error':str(exc)[:400]}
        (out/'research.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        raise SystemExit(result['error'])
    (out/'research.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Fresh three-source draft and independent fact review passed; no Canva/post calls')
