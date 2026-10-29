"""Six distinct editorial layouts, with publication-history based rotation."""
from pathlib import Path
from datetime import date
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
STYLES = ('editorial', 'big-number', 'split', 'notes', 'timeline', 'poster')
PALETTES = {
    'nordic': [('F7F0E4','382E29','BB553B'), ('DDEEE4','183D39','D16F32'),
               ('FFF2E7','432F36','C24B56'), ('F2EEFA','352D4C','7252A2'),
               ('F4F1E5','283D36','537D67'), ('213E36','FFF5DB','EDB45C')],
    'issue': [('F2F4F7','152539','2452CE'), ('152539','F4F7FA','83DBCF'),
              ('F5F1EB','3E2731','A42D4C'), ('EAF0F7','1F3655','32689B'),
              ('FFF4E5','3B3025','B94F20'), ('163BA0','FFFFFF','F5D85D')],
}


def choose_design(kind, publication_id, history, requested=None):
    if requested:
        if requested not in STYLES:
            raise ValueError('Unknown design_id: ' + requested)
        return requested
    recent = [p.get('design_id') for p in sorted(history.values(), key=lambda p: p.get('at',''))
              if p.get('status') in ('published','pending')][-3:]
    slot = date.fromisoformat(publication_id[:10]).toordinal() * 2 + publication_id.endswith('pm')
    pool = [s for s in STYLES if s not in recent]
    return pool[slot % len(pool)]


def font(size, bold=False):
    names = (['C:/Windows/Fonts/malgunbd.ttf','/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc']
             if bold else ['C:/Windows/Fonts/malgun.ttf','/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'])
    for name in names:
        if Path(name).exists(): return ImageFont.truetype(name, size)
    raise RuntimeError('Korean fonts missing')


def lines(d, text, f, width):
    result=[]
    for para in text.split('\n'):
        row=''
        for word in para.split():
            candidate=(row+' '+word).strip()
            if row and d.textlength(candidate,font=f)>width:
                result.append(row); row=word
            else: row=candidate
            while d.textlength(row,font=f)>width:
                cut=1
                while cut<len(row) and d.textlength(row[:cut+1],font=f)<=width: cut+=1
                result.append(row[:cut]);row=row[cut:]
        result.append(row)
    return result


def block(d,text,box,color,size=60,bold=False,minimum=34):
    x,y,right,bottom=box
    for n in range(size,minimum-1,-2):
        f=font(n,bold); rows=lines(d,text,f,right-x); step=int(n*1.48)
        if len(rows)*step<=bottom-y: break
    else: raise ValueError('Text does not fit: '+text[:35])
    for row in rows:
        d.text((x,y),row,font=f,fill=color); y+=step
    return y


def render_design(content,out_dir,kind,design_id,sources=(),date_text=''):
    idx=STYLES.index(design_id)
    bg,ink,accent=('#'+s for s in PALETTES[kind][idx])
    handle='@nordic_log' if kind=='nordic' else '@issue.cards'
    brand='NORDIC LOG' if kind=='nordic' else 'ISSUE / CARDS'
    slides=content['slides']; total=len(slides)+2
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    pages=[]
    for page in range(total):
        im=Image.new('RGB',(W,H),bg);d=ImageDraw.Draw(im)
        d.text((72,48),brand,font=font(28,True),fill=accent)
        d.text((72,1270),handle,font=font(28),fill=ink)
        d.text((880,1270),f'{page+1:02d} / {total:02d}',font=font(28),fill=ink)
        if page==0:
            title,sub=content['cover_title'],content['cover_sub']
            if design_id=='editorial':
                d.line((72,116,1008,116),fill=ink,width=3)
                block(d,title,(72,180,1008,590),ink,104,True)
                block(d,sub,(72,640,780,850),accent,48)
                d.rectangle((72,952,1008,1194),fill=accent)
                block(d,'오늘 살펴볼 '+str(len(slides))+'가지\n'+slides[0]['title'],(108,985,972,1170),bg,42,True)
            elif design_id=='big-number':
                d.text((60,105),f'{len(slides):02d}',font=font(360,True),fill=accent)
                block(d,title,(72,565,1008,940),ink,96,True)
                block(d,sub,(76,1020,1004,1215),ink,44)
            elif design_id=='split':
                d.rectangle((0,170,405,1220),fill=accent)
                block(d,'한눈에\n정리', (50,360,350,820),bg,88,True)
                block(d,title,(455,240,1000,850),ink,80,True)
                block(d,sub,(455,930,1000,1190),accent,42)
            elif design_id=='notes':
                d.rectangle((72,165,1008,1200),fill='#FFFFFF')
                d.rectangle((380,140,700,185),fill=accent)
                block(d,title,(112,240,960,650),ink,90,True)
                block(d,sub,(115,705,960,890),accent,46)
                for j in range(3):d.line((115,1000+j*65,960,1000+j*65),fill=accent,width=2)
            elif design_id=='timeline':
                block(d,title,(72,165,1008,550),ink,94,True)
                block(d,sub,(72,600,1008,780),accent,44)
                d.line((140,860,140,1160),fill=accent,width=6)
                for j,s in enumerate(slides[:3]):
                    yy=850+j*115;d.ellipse((120,yy,160,yy+40),fill=accent)
                    block(d,s['title'],(205,yy-7,990,yy+95),ink,42,True)
            else:
                d.rectangle((72,140,1008,155),fill=accent)
                block(d,title,(72,265,1008,850),ink,116,True)
                block(d,sub,(72,970,1008,1200),accent,48)
        elif page==total-1:
            heading='한 번 더 확인' if kind=='nordic' else '원문을 확인하세요'
            block(d,heading,(72,165,1008,380),ink,82,True)
            items=[s['title'] for s in slides] if kind=='nordic' else list(dict.fromkeys(s['outlet'] for s in sources))
            for j,t in enumerate(items[:5]):
                yy=440+j*125
                d.rectangle((75,yy+12,92,yy+56),fill=accent)
                block(d,t,(130,yy,1000,yy+110),ink,44,True)
            note='필요한 날 다시 꺼내 보세요.' if kind=='nordic' else '출처 링크·확인 시각은 본문에\n'+date_text
            block(d,note,(72,1110,1008,1240),accent,34)
        else:
            item=slides[page-1]
            mode=(idx+page-1)%3
            if mode==0:
                d.text((65,135),f'{page:02d}',font=font(190,True),fill=accent)
                block(d,item['title'],(72,440,1008,720),ink,78,True)
                d.line((72,785,1008,785),fill=accent,width=5)
                block(d,item['body'],(72,845,1008,1210),ink,54)
            elif mode==1:
                d.rectangle((72,170,1008,580),fill=accent)
                block(d,f'{page:02d} / '+item['title'],(110,215,965,545),bg,72,True)
                block(d,item['body'],(100,710,985,1170),ink,58)
            else:
                d.line((120,220,120,1160),fill=accent,width=8)
                d.ellipse((85,215,155,285),fill=accent)
                block(d,item['title'],(205,210,1000,590),ink,78,True)
                block(d,item['body'],(205,680,1000,1175),ink,54)
        path=out_dir/f'{page+1:02d}.jpg';im.save(path,quality=94);pages.append(path)
    return pages
