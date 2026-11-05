"""Real-photo editorial plans. PDF is an interchange; only Canva exports may publish."""
import hashlib
import io
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import requests
from PIL import Image

POLICY = 'impeccable-real-photo-v1'
FONT_URL = 'https://raw.githubusercontent.com/google/fonts/main/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf'


def validate_photo_plan(draft, catalog, height):
    if draft.get('design_policy') != POLICY:
        raise RuntimeError('Impeccable real-photo plan required; synthetic fallback prohibited')
    sections = draft.get('sections', [])
    if not 5 <= len(sections) <= 7:
        raise RuntimeError('Five to seven editorial pages required')
    boxes = []
    photos = []
    for section in sections:
        photo = catalog.get(str(section.get('photo_id')))
        if not photo or photo.get('kind') != 'real_photograph' or not photo.get('license_url') or not photo.get('source_page') or not photo.get('author') or not photo.get('sha256'):
            raise RuntimeError('Every page requires a verified real-photo source and license')
        u = urlsplit(photo['url'])
        if u.scheme != 'https' or u.hostname != 'images.pexels.com' or u.username or u.password or u.port:
            raise RuntimeError('Photo host not approved')
        if section.get('context_label') and section['context_label'] not in section.get('title','')+section.get('body',''):
            raise RuntimeError('News attribution must remain visible in the main wording')
        if not section.get('photo_relation'):
            raise RuntimeError('Photo must explain the page, not decorate it')
        layout = section.get('layout', {})
        occupied = []
        for name in ('photo', 'title', 'body'):
            if name == 'body' and not section.get('body'):
                continue
            box = layout.get(name)
            if not isinstance(box, list) or len(box) != 4 or any(type(v) not in (int, float) for v in box):
                raise RuntimeError('Explicit editorial geometry required')
            x, y, w, h = box
            top = 210 if height == 1920 else 64
            bottom = height - (340 if height == 1920 else 110)
            if min(x, w, h) < 0 or x < 64 or x + w > 1016 or y < top or y + h > bottom:
                raise RuntimeError('Content outside mobile safe area')
            for other in occupied:
                ox, oy, ow, oh = other
                if not (x + w + 24 <= ox or ox + ow + 24 <= x or y + h + 24 <= oy or oy + oh + 24 <= y):
                    raise RuntimeError('Text/photo collision or separation below24px')
            occupied.append(box)
        if not 64 <= layout.get('title_size', 0) <= 100 or not 44 <= layout.get('body_size', 0) <= 56:
            raise RuntimeError('Mobile text too small or unbounded')
        if layout['photo'][2] * layout['photo'][3] < 1080 * height * .18:
            raise RuntimeError('Photo must have a meaningful visual role')
        boxes.append(tuple(layout['photo']))
        photos.append(str(section['photo_id']))
    if len(set(boxes)) < 3 or len(set(photos)) < 3:
        raise RuntimeError('Repeated photo/layout production prohibited')
    return draft


def photo_draft_prompt(catalog, kind):
    return ('Use the official Impeccable hierarchy, precise typography, meaningful whitespace and mobile adaptation principles. '
        'Create bespoke layouts, never a fixed template rotation. EVERY page must include an UNALTERED REAL photograph '
        'from this vetted catalog, no synthetic photos, no invented before/after or claims that these are the same home. '
        'Choose a practical topic supported by the ACTUAL visible objects. Return existing draft fields plus '
        'design_policy="'+POLICY+'". In EACH section include photo_id, photo_relation explaining the semantic match, '
        'and layout:{photo:[x,y,w,h],title:[x,y,w,h],body:[x,y,w,h],title_size:72,body_size:46}. '
        'Coordinates are1080 wide and '+str(1350 if kind=='carousel' else 1920)+' high. '
        'Keep all boxes x64..1016; y64..1240 for cards or y210..1580 for videos; separate ALL boxes by24px. '
        'Photos use CONTAIN preserving the entire original frame, never crop important objects. Photo area at least18% '
        'of page, at least3 different actual photos and3 different photo geometries. No text on photos. '
        'Use explicit newline breaks inside title/body to fit; body font44-56px and title64-100px. '
        'Keep video title under12 Korean characters and body under18, hook body empty; no reading overload. '
        'White/cool-gray/charcoal, tiny restrained blue accent, no ornamental rules, no emoji, no generic boxes. '
        'Caption credits real photographers; no false AI-photo disclosure. AI-assisted layout/copy may be disclosed. '
        'Photo catalog JSON='+json.dumps(catalog, ensure_ascii=False))


def make_pdf(draft, catalog, height, destination, cache):
    """Embed original photo pixels and vector text separately, then import into Canva."""
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.utils import ImageReader
    validate_photo_plan(draft, catalog, height)
    cache = Path(cache); cache.mkdir(parents=True, exist_ok=True)
    font = cache / 'NotoSansKR.ttf'
    if not font.exists():
        response = requests.get(FONT_URL, timeout=60, allow_redirects=False)
        response.raise_for_status(); font.write_bytes(response.content)
    from fontTools.ttLib import TTFont as VariableFont
    from fontTools.varLib.instancer import instantiateVariableFont
    for weight, name in ((700, 'NordicHeading'), (450, 'NordicBody')):
        static = cache / f'NotoSansKR-{weight}.ttf'
        if not static.exists():
            variable = VariableFont(str(font))
            instantiateVariableFont(variable, {'wght': weight}, inplace=True).save(str(static))
        pdfmetrics.registerFont(TTFont(name, str(static)))
    c = canvas.Canvas(str(destination), pagesize=(1080, height), pageCompression=1)
    evidence = []
    for section in draft['sections']:
        photo = catalog[str(section['photo_id'])]
        local = cache / (str(section['photo_id']) + '.jpg')
        if not local.exists():
            response = requests.get(photo['url'], timeout=60, allow_redirects=False)
            response.raise_for_status()
            if len(response.content) > 12_000_000:
                raise RuntimeError('Photo exceeds bounded asset size')
            local.write_bytes(response.content)
        data = local.read_bytes()
        if hashlib.sha256(data).hexdigest() != photo['sha256']:
            raise RuntimeError('Real-photo source changed; review before use')
        im = Image.open(io.BytesIO(data)); im.load()
        if min(im.size) < 900:
            raise RuntimeError('Actual photo resolution insufficient')
        c.setFillColorRGB(1, 1, 1); c.rect(0, 0, 1080, height, fill=1, stroke=0)
        layout = section['layout']; x, y, w, h = layout['photo']
        scale = min(w / im.width, h / im.height)
        dw, dh = im.width * scale, im.height * scale
        px, py = x + (w-dw)/2, y + (h-dh)/2
        c.drawImage(ImageReader(io.BytesIO(data)), px, height-py-dh, dw, dh)
        for key in ('title', 'body'):
            text = section.get(key, '')
            if not text: continue
            tx, ty, tw, th = layout[key]; size = layout[key+'_size']; leading = size*1.32
            lines = text.split('\n')
            face = 'NordicHeading' if key == 'title' else 'NordicBody'
            if len(lines)*leading > th or any(pdfmetrics.stringWidth(line, face, size) > tw for line in lines):
                raise RuntimeError('Text exceeds its measured box: '+key)
            c.setFillColorRGB(*((.11,.14,.16) if key=='title' else (.27,.33,.38)))
            c.setFont(face, size)
            for n, line in enumerate(lines):
                c.drawString(tx, height-ty-size-n*leading, line)
        c.setFont('NordicBody', 28); c.setFillColorRGB(.28,.37,.44)
        footer_y = 290 if height == 1920 else 64
        c.drawString(72, footer_y, '@nordic_log' if draft.get('account','nordic_log')=='nordic_log' else '@issue.cards')
        c.setFont('NordicBody', 23)
        c.drawRightString(1008, footer_y, '사진 '+photo['author']+' / Pexels')
        c.showPage()
        evidence.append({'photo_id':section['photo_id'],'source_page':photo['source_page'],'author':photo['author'],
                         'license_url':photo['license_url'],'source_sha256':photo['sha256'],
                         'crop':'contain: entire original photograph','photo_frame':[px,py,dw,dh],
                         'photo_relation':section['photo_relation']})
    c.save()
    return evidence


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('request'); parser.add_argument('output'); parser.add_argument('--cache',default='outputs/photo-cache')
    args=parser.parse_args(); wrapper=json.loads(Path(args.request).read_text(encoding='utf-8')); request=wrapper.get('request',wrapper)
    evidence=make_pdf(request.get('draft',request),request['photo_catalog'],request['height'],args.output,args.cache)
    Path(str(args.output)+'.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
