"""Render a per-story scene plan, without Canva sessions or a fixed template cycle.

Rendering never marks a story reviewed. The operating agent must inspect every
full-size PNG and 390px proof, record hashes/checks, then run `accept`.
Only local Pillow/font resources are used; no API calls, paid generation or posts.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent
W, H = 1080, 1350
CHECKS = ('text', 'no_obstruction', 'readable_390', 'facts', 'variety', 'canva_quality')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def font(size, bold=False):
    weight = 'Bold' if bold else 'Regular'
    candidates = [f'/usr/share/fonts/opentype/noto/NotoSansCJK-{weight}.ttc',
                  f'/usr/share/fonts/truetype/noto/NotoSansCJK-{weight}.ttc',
                  'C:/Windows/Fonts/malgunbd.ttf' if bold else 'C:/Windows/Fonts/malgun.ttf',
                  f'/System/Library/Fonts/AppleSDGothicNeo.ttc']
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise ValueError('A Korean font is required; do not substitute a missing-glyph font')


def box(element):
    x, y, w, h = element['box']
    if w <= 0 or h <= 0 or x < 0 or y < 0 or x+w > W or y+h > H:
        raise ValueError('Element outside page: '+str(element.get('id')))
    return x, y, x+w, y+h


def intersects(a, b, gap=0):
    return a[0] < b[2]+gap and b[0] < a[2]+gap and a[1] < b[3]+gap and b[1] < a[3]+gap


def contains(outer, inner, padding=24):
    return (inner[0] >= outer[0]+padding and inner[1] >= outer[1]+padding
            and inner[2] <= outer[2]-padding and inner[3] <= outer[3]-padding)


def wrap(draw, text, f, width):
    lines = []
    for paragraph in text.split('\n'):
        line = ''
        for char in paragraph:
            if line and draw.textlength(line+char, font=f) > width:
                # Prefer a word boundary, otherwise split Korean at a character.
                cut = line.rfind(' ')
                if cut > len(line)//2:
                    lines.append(line[:cut]); line = line[cut+1:]+char
                else:
                    lines.append(line); line = char
            else:
                line += char
        lines.append(line.strip())
    return lines


def text_layout(draw, e):
    x0, y0, x1, y1 = box(e)
    minimum = 28 if e.get('role') == 'meta' else 38
    size = int(e.get('size', 48)); floor = int(e.get('min_size', size))
    if floor < minimum or size < floor:
        raise ValueError('Font below readable minimum: '+e['id'])
    for n in range(size, floor-1, -1):
        f = font(n, e.get('bold', False)); lines = wrap(draw, e['text'], f, x1-x0)
        ascent, descent = f.getmetrics(); step = ascent+descent+int(e.get('gap', 12))
        used = step*len(lines)-int(e.get('gap', 12))
        if used <= y1-y0 and all(draw.textlength(s,font=f) <= x1-x0 for s in lines):
            runs=[]
            for i, line in enumerate(lines):
                length=draw.textlength(line,font=f)
                x=x0 if e.get('align') != 'center' else x0+(x1-x0-length)/2
                y=y0+i*step
                runs.append((x,y,line))
            return f, runs, (x0,y0,x1,y0+used)
    raise ValueError('Text overflow; rewrite or recompose: '+e['id'])


def render_page(page, handle):
    im=Image.new('RGB',(W,H),page.get('background','#FFFFFF'));draw=ImageDraw.Draw(im)
    elements=list(page['elements'])
    elements.append({'id':'account-footer','type':'text','role':'meta','text':handle,
                     'box':[64,1275,950,55],'size':28,'color':page.get('footer_color','#536171')})
    ids=[e['id'] for e in elements]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate element IDs')
    texts=[];visuals=[];panels=[]
    for e in elements:
        b=box(e);kind=e['type']
        if kind == 'text':
            if e.get('decoration') or e.get('strikethrough'):
                raise ValueError('Text decorations are not supported')
            f,runs,ink=text_layout(draw,e);texts.append((e,f,runs,ink))
        elif kind == 'panel':
            panels.append(b)
            draw.rounded_rectangle(b,radius=e.get('radius',0),fill=e['fill'])
        elif kind in ('rect','ellipse'):
            visuals.append(b)
            getattr(draw,'rectangle' if kind=='rect' else 'ellipse')(b,fill=e['fill'])
        elif kind == 'image':
            if not e.get('rights'):
                raise ValueError('Image rights/source note required')
            path=(ROOT/e['path']).resolve();path.relative_to(ROOT)
            visuals.append(b)
            with Image.open(path) as source:
                source=ImageOps.fit(source.convert('RGB'),(int(b[2]-b[0]),int(b[3]-b[1])))
                im.paste(source,(int(b[0]),int(b[1])))
        else:
            raise ValueError('Unsupported element (decorative lines prohibited): '+kind)
    for i,(e,f,runs,b) in enumerate(texts):
        if any(intersects(b,other[3],24) for other in texts[i+1:]):
            raise ValueError('Text collision: '+e['id'])
        if any(intersects(b,v,24) for v in visuals):
            raise ValueError('Image/shape too close to text: '+e['id'])
        if any(intersects(b,p,24) and not contains(p,b) for p in panels):
            raise ValueError('Text touches panel edge: '+e['id'])
        for x,y,line in runs:
            draw.text((x,y),line,font=f,fill=e.get('color','#202730'),anchor='lt')
    return im


def build(payload_path, plan_path, out):
    p=read(payload_path);plan=read(plan_path);out=Path(out).resolve()
    out.relative_to((ROOT/'images').resolve())
    if plan['account'] != ('nordic' if ROOT.name == 'cardnews' else 'issue'):
        raise ValueError('Plan account does not match this project')
    if plan['publication_id'] != p['id'] or len(plan['pages']) not in range(5,8):
        raise ValueError('Plan must match payload and contain 5-7 pages')
    for key in ('message','rationale','recent9_comparison'):
        if not plan.get(key):
            raise ValueError('Missing editorial decision: '+key)
    roles=[page.get('role') for page in plan['pages']]
    if len(set(roles)) < 3 or not all(roles):
        raise ValueError('Use distinct cover, explanation and conclusion compositions')
    norm=lambda t: ''.join(t.split())
    corpus=norm(''.join(e.get('text','') for page in plan['pages'] for e in page['elements']))
    c=p['content'];required=[c['cover_title'],c['cover_sub']]
    required += [s[k] for s in c['slides'] for k in ('title','body')]
    if any(norm(t) not in corpus for t in required):
        raise ValueError('Plan is missing exact reviewed manuscript text')
    handle={'nordic':'@nordic_log','issue':'@issue.cards'}[plan['account']]
    # Render all pages in memory first: invalid page 5 cannot leave a mixed batch.
    pages=[render_page(page,handle) for page in plan['pages']]
    out.mkdir(parents=True,exist_ok=True);assets=[]
    for i,im in enumerate(pages,1):
        path=out/f'{i:02}.png';im.save(path)
        im.resize((390,488),Image.Resampling.LANCZOS).save(out/f'{i:02}-390.png')
        assets.append({'path':path.relative_to(ROOT).as_posix(),'sha256':digest(path)})
    review={'renderer':'editorial-scene-v1','publication_id':p['id'],'plan_sha256':digest(plan_path),
            'payload_sha256':digest(payload_path),'assets':assets,
            'quality_benchmark':'',
            'pages':[dict(asset,quality_notes='',**{k:False for k in CHECKS}) for asset in assets]}
    write(out/'review.json',review)
    print('Rendered',len(assets),'pages. Inspect every full-size and 390px image, then record review checks.')


def accept(payload_path, plan_path, review_path, output):
    p=read(payload_path);r=read(review_path)
    if (r['publication_id'] != p['id'] or r['plan_sha256'] != digest(plan_path)
            or r['payload_sha256'] != digest(payload_path) or len(r['pages']) != len(r['assets'])):
        raise ValueError('Stale review; render/review again')
    if not 5 <= len(r['assets']) <= 7 or len({a['path'] for a in r['assets']}) != len(r['assets']):
        raise ValueError('Expected 5-7 distinct reviewed pages')
    if not str(r.get('quality_benchmark','')).strip():
        raise ValueError('Name a verified Canva quality benchmark before accepting')
    for asset,checks in zip(r['assets'],r['pages']):
        path=(ROOT/asset['path']).resolve();path.relative_to((ROOT/'images').resolve())
        if (asset['path'] != checks['path'] or asset['sha256'] != checks['sha256']
                or digest(path) != asset['sha256'] or any(checks.get(k) is not True for k in CHECKS)
                or len(str(checks.get('quality_notes','')).strip()) < 20):
            raise ValueError('Incomplete visual review or changed export')
    p.update(reviewed=True,design_status='editorial_all_pages_reviewed',exported_assets=r['assets'],
             design_review={'renderer':r['renderer'],'plan_sha256':r['plan_sha256'],
                            'quality_benchmark':r['quality_benchmark'],'pages':r['pages']})
    p.pop('canva_design_id',None)
    write(output,p);print('Prepared reviewed file:',output,'(no publication performed)')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['render','accept'])
    parser.add_argument('--payload',required=True);parser.add_argument('--plan',required=True)
    parser.add_argument('--out');parser.add_argument('--review')
    args=parser.parse_args()
    if args.action == 'render':
        if not args.out:parser.error('--out required')
        build(args.payload,args.plan,args.out)
    else:
        if not args.review or not args.out:parser.error('--review and --out required')
        accept(args.payload,args.plan,args.review,args.out)
