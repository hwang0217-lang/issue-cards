"""Engineering transport only: no Canva/news claim and no Instagram credential."""
import hashlib,json,subprocess
from datetime import datetime
import requests
from cloud_reel import OUT,FFMPEG,KST
from autonomous_media import approved_music
from media_delivery import stage_video

def main():
    OUT.mkdir(exist_ok=True)
    music,track=approved_music('clean',OUT,datetime.now(KST).date().isoformat())
    file=OUT/'transport-engineering-only.mp4'
    subprocess.run([FFMPEG,'-v','error','-y','-f','lavfi','-i','color=c=white:s=1080x1920:r=30',
        '-i',str(music),'-t','2','-c:v','libx264','-preset','ultrafast','-threads','2','-pix_fmt','yuv420p',
        '-c:a','aac','-movflags','+faststart',str(file)],check=True,capture_output=True)
    report={'purpose':'engineering transport only, not news or a finished design','published':False,
            'instagram_calls':0,'pc_media_downloads':0,'music_track':track,'music_sha256_verified':True}
    def save():(OUT/'transport-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    url=stage_video(file,report,save)
    response=requests.get(url,timeout=45,allow_redirects=False)
    if not response.ok or hashlib.sha256(response.content).hexdigest()!=hashlib.sha256(file.read_bytes()).hexdigest():
        raise RuntimeError('Complete cloud byte verification failed')
    report['complete_cloud_fetch_hash_verified']=True;report['stage']='transport_verified';save()
    print('Approved music and temporary cloud delivery hashes verified; Instagram calls zero')

if __name__=='__main__':main()
