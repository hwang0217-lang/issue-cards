"""Runner-only editing and official Instagram URL delivery. No PC media file."""
import hashlib
import json
import os
import re
import subprocess
import time
from urllib.parse import urlparse
from datetime import datetime
import requests
from cloud_reel import FFMPEG, KST, PublicationState, enforce_publish, graph

def ensure_detail_crops(pages, draft):
    from gemini_editor import generate_json
    from PIL import Image
    from itertools import combinations
    import io
    def jpeg(path):
        image=Image.open(path).convert('RGB');buffer=io.BytesIO();image.save(buffer,'JPEG',quality=90);return buffer.getvalue()
    seconds=[max(3.5,min(7,(len(s['title'])+len(s.get('body','')))/7+1.5)) for s in draft['sections']]
    choices={}
    for count in (2,3):
        for middle in combinations(range(2,len(pages)),count):
            selected=[1,*middle,len(pages)]
            if sum(seconds[i-1] for i in selected)+2<=27:
                choices['choice_'+str(len(choices)+1)]=selected
    if not choices:raise RuntimeError('Script cannot fit readable timing; shorten wording, never speed up')
    selection_schema={'type':'object','required':['choice','safe','reason'],'properties':{
        'choice':{'type':'string','enum':list(choices)},'safe':{'type':'boolean'},'reason':{'type':'string'}}}
    selection,_=generate_json('Select a concise coherent photo-Reel sequence from these ACTUAL page texts. '
        'Every option already preserves the first hook and last CTA and enough reading time. Choose the '
        'option that omits only redundant/supporting explanation, not an essential action. If no option '
        'preserves essential meaning, safe=false. Return choice, safe, reason. Options JSON: '+json.dumps(choices)+
        ' Page texts JSON: '+json.dumps([{'page':i+1,'title':v['title'],'body':v.get('body','')} for i,v in enumerate(draft['sections'])],ensure_ascii=False),schema=selection_schema)
    if selection.get('safe') is not True or selection.get('choice') not in choices:
        raise RuntimeError('Story selection would remove essential information')
    selected=choices[selection['choice']];draft['scene_indices']=selected
    crop_pages=[1,selected[1]]
    rectangle={'type':'object','required':['x','y','w','h','observations'],'properties':{
        **{k:{'type':'number','minimum':0,'maximum':1000} for k in ('x','y','w','h')},'observations':{'type':'string'}}}
    schema={'type':'object','required':['coordinate_space','first','second'],'properties':{
        'coordinate_space':{'type':'string','enum':['normalized_1000']},'first':rectangle,'second':rectangle}}
    boxes,_=generate_json('Inspect ONLY these TWO actual finished images in order. Return ONE photo-only '
        'rectangle well inside each image: first for image1, second for image2. Do NOT choose lettering, '
        'blank areas or invented objects. Describe the actual photographed objects inside each crop. '
        'x,y,w,h MUST be NORMALIZED0-1000 relative to the full image, not pixels. No page selection is needed.',
        [jpeg(pages[i-1]) for i in crop_pages],schema=schema)
    if boxes.get('coordinate_space')!='normalized_1000':raise RuntimeError('Explicit normalized coordinate system required')
    crops=[]
    for page,key in zip(crop_pages,('first','second')):
        box=boxes.get(key,{});values=[box.get(k) for k in ('x','y','w','h')]
        if any(type(v) not in (int,float) for v in values) or not box.get('observations'):
            raise RuntimeError('Actual photo rectangle and observations required')
        x,y,w,h=values
        if not (0<=x<x+w<=1000 and 0<=y<y+h<=1000 and w>=120 and h>=120):
            raise RuntimeError('Photo crop outside actual final image')
        pixels={'x':x*1080/1000,'y':y*1920/1000,'w':w*1080/1000,'h':h*1920/1000}
        draft['sections'][page-1]['detail_crop']=pixels
        crops.append({'page':page,'normalized':box,'pixels':pixels})
    result={'scene_indices':selected,'story_selection':selection,'crops':crops}
    from cloud_reel import OUT
    OUT.mkdir(exist_ok=True)
    (OUT/'autonomous-crop-response.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def video_review_prompt(kind):
    common=('Inspect the COMPLETE actual encoded video including music; do not infer its content from an '
        'intended script. Return JSON verdict pass/revise, readable, no_overlap, full_video_checked, '
        'music_present, edit_quality, meaningful_motion, literal_subjects, notes. Read actual screen text '
        'and verify enough time remains to read each message. Reject black/blank/unrelated frames or cropped text. ')
    if kind=='reel':
        return common+('This is a PHOTO/USE-SCENE REEL. Object photographs, closeups, detail cutaways and '
            'subtle reframing are the intended format. It is NOT an information motion graphic, so animated '
            'diagrams are not required. Judge the actual cutaways and pacing; reject a mere unchanged five-card '
            'equal-duration slideshow. Do NOT fail this photo Reel for lacking animated information relationships.')
    return common+('This is an INFORMATION MOTION graphic. Require an actual diagram/sequence/comparison '
        'relationship to be progressively revealed with adequate reading hold. Photos plus zoom alone cannot pass.')

def ensure_motion_regions(pages, draft):
    """Bind each detection to its actual body page; hook/CTA need not be diagrams."""
    from gemini_editor import generate_json
    from PIL import Image
    import io
    schema={'type':'object','required':['can_animate','notes','regions'],'properties':{
        'can_animate':{'type':'boolean'},'notes':{'type':'string'},
        'regions':{'type':'array','maxItems':4,'items':{'type':'object',
            'required':['x','y','w','h','bg','at_seconds','role'],'properties':{
                **{k:{'type':'number','minimum':0,'maximum':1000} for k in ('x','y','w','h')},
                'bg':{'type':'string'},'at_seconds':{'type':'number','minimum':0.5,'maximum':1.5},'role':{'type':'string'}}}}}}
    reviews=[];animated=0
    for index in range(1,len(pages)-1):
        image=Image.open(pages[index]).convert('RGB');buffer=io.BytesIO();image.save(buffer,'JPEG',quality=90)
        review,_=generate_json('Inspect this ONE actual finished information graphic. Can parts of an '
            'actual comparison/sequence/relationship be revealed in order to explain meaning? Photos or '
            'a title alone do not qualify. If no real diagram or no flat matching background, can_animate=false. '
            'Otherwise return2-4 rectangles for actual diagram parts, not paragraphs, with NORMALIZED0-1000 '
            'coordinates, exact flat background hex, meaningful role and reveal delay0.5-1.5sec. No invented regions.',
            [buffer.getvalue()],schema=schema)
        reviews.append({'page':index+1,**review})
        if review.get('can_animate') is not True:continue
        regions=review.get('regions',[])
        if len(regions)<2:raise RuntimeError('An information sequence requires at least two real diagram regions')
        converted=[]
        for region in regions:
            values=[region.get(k) for k in ('x','y','w','h','at_seconds')]
            if any(type(v) not in (int,float) for v in values):raise RuntimeError('Numeric diagram coordinates required')
            x,y,w,h,delay=values
            if (not (0<=x<x+w<=1000 and 0<=y<y+h<=1000 and w>0 and h>0 and 0.5<=delay<=1.5) or
                    not re.fullmatch(r'#[0-9a-fA-F]{6}',region.get('bg','')) or not region.get('role')):
                raise RuntimeError('Invalid observed diagram region')
            converted.append({**region,'x':x*1080/1000,'y':y*1920/1000,'w':w*1080/1000,'h':h*1920/1000})
        draft['sections'][index]['reveal_regions']=converted;animated+=1
    if animated<2:raise RuntimeError('At least two actual information-motion body pages required; no photo-zoom substitute')
    return reviews

def approved_music(mood, directory, day):
    tracks = json.loads(os.environ.get('ISSUE_APPROVED_MUSIC', '[]'))
    if len(tracks) != 10: raise RuntimeError('Approved ten-track server library missing')
    choices = [t for t in tracks if t['mood'] == mood]
    if not choices: raise RuntimeError('Requested music mood unavailable')
    track = choices[datetime.fromisoformat(day).toordinal() % len(choices)]
    u = urlparse(track['url'])
    if u.scheme != 'https' or u.username or u.password or u.port or not u.hostname:
        raise RuntimeError('Invalid approved music URL')
    print('::add-mask::' + track['url'])
    r = requests.get(track['url'], timeout=90, allow_redirects=False)
    if not r.ok or len(r.content) > 20_000_000 or hashlib.sha256(r.content).hexdigest() != track['sha256']:
        raise RuntimeError('Approved music bytes unavailable or changed; no generation fallback')
    path = directory / 'approved-music.mp3'; path.write_bytes(r.content)
    return path, track['id']

def render_video(pages, draft, directory, day):
    """Canva is the final visual source; only cropping/reveal/edit/music happen here."""
    selected=draft.get('scene_indices')
    if selected:
        pages=[pages[i-1] for i in selected]
        draft={**draft,'sections':[draft['sections'][i-1] for i in selected]}
    durations = [max(3.5, min(7, (len(s['title']) + len(s.get('body', ''))) / 7 + 1.5)) for s in draft['sections']]
    if sum(durations) > 29: raise RuntimeError('Too much text; edit the script instead of speeding up cuts')
    mood=draft.get('music_mood')
    if mood not in ('warm','bright','playful','calm','clean'):
        text=json.dumps(draft,ensure_ascii=False)
        mood=next((m for m,words in [('calm',('휴식','저녁')),('playful',('실수','공감')),('clean',('비교','단위')),('bright',('정리','수납','동선'))] if any(w in text for w in words)),'warm')
    music, track = approved_music(mood, directory, day)
    clips = []; insert_seconds = 0; inserts = 0
    for n, (page, seconds) in enumerate(zip(pages, durations)):
        clip = directory / f'clip-{n:02d}.mp4'
        frames = round(seconds * 30)
        # A brief detail view pulls back to the complete readable composition; then holds.
        # Final motion suitability is reviewed on the whole encoded video, never inferred here.
        vf = ("scale=1080:1920,zoompan=z='if(lte(on,24),1.06-0.0025*on,1)':"
              "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=" + str(frames) + ":s=1080x1920:fps=30,format=yuv420p")
        regions=draft['sections'][n].get('reveal_regions',[])
        if regions:
            vf='scale=1080:1920,loop=loop='+str(frames-1)+':size=1:start=0,setpts=N/(30*TB),format=yuv420p'
            for region in regions:
                x,y,w,h=[region.get(k) for k in ('x','y','w','h')]
                delay=region.get('at_seconds');color=region.get('bg','')
                if (any(type(v) not in (int,float) for v in (x,y,w,h,delay)) or
                        not (0<=x<x+w<=1080 and 0<=y<y+h<=1920 and w>0 and h>0 and 0.5<=delay<=1.5) or
                        not re.fullmatch(r'#[0-9a-fA-F]{6}',color) or not region.get('role')):
                    raise RuntimeError('Invalid actual-diagram reveal region')
                vf+=f",drawbox=x={round(x)}:y={round(y)}:w={round(w)}:h={round(h)}:color=0x{color[1:]}:t=fill:enable='lt(t,{delay})'"
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-i', str(page), '-vf', vf, '-an',
                        '-r','30','-frames:v',str(frames),'-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-threads', '2', str(clip)],
                       check=True, capture_output=True)
        clips.append(clip)
        crop = draft['sections'][n].get('detail_crop')
        if crop and inserts < 2 and n < len(pages)-1:
            x,y,w,h=[crop.get(k) for k in ('x','y','w','h')]
            if (any(type(v) not in (int,float) for v in (x,y,w,h)) or
                    not (0<=x<x+w<=1080 and 0<=y<y+h<=1920 and w>=120 and h>=120)):
                raise RuntimeError('Detail crop must identify an actual photo rectangle')
            detail=directory/f'detail-{n:02d}.mp4'
            subprocess.run([FFMPEG,'-v','error','-y','-loop','1','-i',str(page),'-t','1',
                '-vf',f'crop={round(w)}:{round(h)}:{round(x)}:{round(y)},scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p',
                '-r','30','-c:v','libx264','-threads','2','-preset','fast','-crf','20',str(detail)],check=True,capture_output=True)
            clips.append(detail);inserts+=1;insert_seconds+=1

    listing = directory / 'concat.txt'
    listing.write_text('\n'.join("file '" + p.name + "'" for p in clips))
    target = directory / 'server-only.mp4'
    total = sum(round(s * 30) / 30 for s in durations) + insert_seconds
    subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(listing),
                    '-i', str(music), '-filter_complex',
                    f'[1:a]volume=0.5,afade=t=in:d=0.2,afade=t=out:st={total-1}:d=1[a]',
                    '-map', '0:v', '-map', '[a]', '-t', str(total), '-c:v', 'copy', '-c:a', 'aac',
                    '-b:a', '160k', '-movflags', '+faststart', str(target)], check=True, capture_output=True)
    subprocess.run([FFMPEG, '-v', 'error', '-i', str(target), '-f', 'null', '-'], check=True, capture_output=True)
    return target, {'duration_seconds': total, 'scene_seconds': durations, 'music_track': track,
                    'video_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                    'selected_original_pages':selected,'edit_segments': len(clips), 'canva_visual_source': True, 'full_decode': True, 'pc_video_download': False}

def require_upload_target(uri, container_id):
    u = urlparse(uri)
    if (u.scheme != 'https' or u.hostname != 'rupload.facebook.com' or u.username or u.password or
            u.port or u.query or u.fragment or not re.fullmatch(r'\d+', str(container_id)) or
            not re.fullmatch(r'/ig-api-upload/v\d+\.\d+/' + str(container_id), u.path)):
        raise RuntimeError('Untrusted resumable destination; no credential sent')
    return uri

def deliver_video(file, plan, mode, row, persist):
    identity = graph('GET', 'me?fields=id,username')
    if identity.get('username') != 'issue.cards': raise RuntimeError('Wrong account')
    if os.environ.get('PUBLISH_PAUSED', '1') != '0': raise RuntimeError('Account paused')
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    state = PublicationState(); key = datetime.now(KST).date().isoformat() + '-cloud'
    if mode == 'publish':
        journals = [state.read('' + n)[0] for n in ('managed-state.json', 'reels-state.json')]
        posts = graph('GET', 'me/media?fields=id,permalink,timestamp&limit=15').get('data', [])
        enforce_publish(plan, digest, posts, journals, datetime.now(KST))
        state.put('managed-state.json', key, {'status': 'pending', 'at': datetime.now(KST).isoformat(),
                  'canva_design_id': plan['canva_design_id'], 'format': plan['format'], 'sha256': digest}, absent=True)
    from media_delivery import stage_video
    url=stage_video(file,row,persist)
    row['upload_status'] = 'creating'; persist()
    session = graph('POST', identity['id'] + '/media', {'media_type': 'REELS', 'video_url': url,
        'caption': plan['caption'], 'share_to_feed': 'true', 'is_ai_generated': 'true', 'thumb_offset': '1000'})
    row.update(container_id=session['id'], upload_status='processing'); persist()
    for _ in range(80):
        status = graph('GET', session['id'] + '?fields=status_code')['status_code']
        if status == 'FINISHED': break
        if status in ('ERROR', 'EXPIRED'): raise RuntimeError('Instagram rejected prepared video')
        time.sleep(5)
    else: raise RuntimeError('Instagram processing pending; reconcile existing container')
    row.update(upload_status='FINISHED', published=False); persist()
    if mode != 'publish': return
    row['upload_status'] = 'publishing'; persist()
    media = graph('POST', identity['id'] + '/media_publish', {'creation_id': session['id']})
    row['media_id'] = media['id']; persist()
    actual = graph('GET', media['id'] + '?fields=id,permalink,media_product_type,timestamp,media_url')
    if actual.get('media_product_type') != 'REELS' or not actual.get('permalink'):
        raise RuntimeError('Public result uncertain; never repeat')
    row.update(published=True, permalink=actual['permalink'], upload_status='published_verified'); persist()
    entry = {'status': 'published', 'at': actual['timestamp'], 'canva_design_id': plan['canva_design_id'],
             'format': plan['format'], 'sha256': digest, 'permalink': actual['permalink'], 'media_id': media['id']}
    for name in ('managed-state.json', 'reels-state.json'): state.put('' + name, key, entry)
    # Public result verification happens after durable publication recording. A playback
    # error can never cause a second publish, and the media never reaches the user's PC.
    if not actual.get('media_url'): raise RuntimeError('Published ID recorded; playback URL verification unavailable')
    print('::add-mask::' + actual['media_url'])
    r=requests.get(actual['media_url'],timeout=120,allow_redirects=False)
    if not r.ok or len(r.content)>150_000_000: raise RuntimeError('Published media recorded; playback retrieval needs review')
    verified=file.with_name('public-transcode-check.mp4');verified.write_bytes(r.content)
    subprocess.run([FFMPEG,'-v','error','-i',str(verified),'-f','null','-'],check=True,capture_output=True)
    row['public_playback_decode_verified']=True;persist()
