"""뉴스 카드뉴스를 1080x1350 이미지 7장으로 그린다. 사진 없이 글자와 도형 중심의 그래픽 디자인."""
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
NAVY = (14, 20, 32)
NAVY_2 = (24, 33, 50)
YELLOW = "#FFD84A"
INK = "#10151F"
WHITE = "#FFFFFF"
SOFT = "#AEB8CA"
LINE = "#2E3A52"
HANDLE = os.environ.get("IG_HANDLE", "@issue.cards")
MARGIN = 70

BOLD_FONTS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "C:/Windows/Fonts/malgunbd.ttf",
]
BLACK_FONTS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Black.ttc",
] + BOLD_FONTS
REGULAR_FONTS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "C:/Windows/Fonts/malgun.ttf",
]

SLIDE_LABELS = ["무슨 일인가요", "왜 이슈인가요", "핵심 내용", "영향은", "앞으로는"]


def font(paths, size):
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    raise FileNotFoundError("한글 글꼴을 찾지 못했어요")


# ---------- 글자 배치 ----------

def norm(text: str) -> str:
    return " ".join(text.split())


def wrap_spans(draw, text, fnt, max_width):
    spans, line_start, line_end = [], None, None
    pos = 0
    for word in text.split(" "):
        w_start, w_end = pos, pos + len(word)
        pos = w_end + 1
        if not word:
            continue
        if line_start is None:
            line_start, line_end = w_start, w_end
        elif draw.textlength(text[line_start:w_end], font=fnt) <= max_width:
            line_end = w_end
        else:
            spans.append((line_start, line_end))
            line_start, line_end = w_start, w_end
        while draw.textlength(text[line_start:line_end], font=fnt) > max_width:
            cut = line_start + 1
            while cut < line_end and draw.textlength(text[line_start:cut + 1], font=fnt) <= max_width:
                cut += 1
            spans.append((line_start, cut))
            line_start = cut
    if line_start is not None:
        spans.append((line_start, line_end))
    return spans


def text_height(draw, text, fnt, max_width, gap):
    n = len(wrap_spans(draw, norm(text), fnt, max_width))
    return n * fnt.size + max(0, n - 1) * gap


def draw_text(draw, text, fnt, x, y, max_width, fill, gap, last_fill=None):
    text = norm(text)
    spans = wrap_spans(draw, text, fnt, max_width)
    for i, (s, e) in enumerate(spans):
        color = last_fill if (last_fill and i == len(spans) - 1) else fill
        draw.text((x, y), text[s:e], font=fnt, fill=color)
        y += fnt.size + gap
    return y - gap


def draw_highlighted(draw, text, highlight, fnt, x, y, max_width, gap, fill=WHITE):
    text = norm(text)
    hl = norm(highlight or "")
    h_start = text.find(hl) if hl else -1
    h_end = h_start + len(hl) if h_start >= 0 else -1
    for s, e in wrap_spans(draw, text, fnt, max_width):
        a, b = max(s, h_start), min(e, h_end)
        if h_start >= 0 and a < b:
            x0 = x + draw.textlength(text[s:a], font=fnt)
            x1 = x + draw.textlength(text[s:b], font=fnt)
            draw.rectangle((x0 - 4, y + 2, x1 + 4, y + fnt.size + 8), fill=YELLOW)
            draw.text((x, y), text[s:a], font=fnt, fill=fill)
            draw.text((x0, y), text[a:b], font=fnt, fill=INK)
            draw.text((x1, y), text[b:e], font=fnt, fill=fill)
        else:
            draw.text((x, y), text[s:e], font=fnt, fill=fill)
        y += fnt.size + gap
    return y - gap


# ---------- 바탕과 부품 ----------

def background(top=NAVY, bottom=NAVY_2) -> Image.Image:
    grad = Image.new("RGB", (1, H))
    for y in range(H):
        t = y / (H - 1)
        grad.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return grad.resize((W, H))


def pill(d, x, y, text, fnt, fill, color, pad_x=28, pad_y=12):
    tw = d.textlength(text, font=fnt)
    d.rounded_rectangle((x, y, x + tw + pad_x * 2, y + fnt.size + pad_y * 2), 40, fill=fill)
    d.text((x + pad_x, y + pad_y - 2), text, font=fnt, fill=color)


def footer(d, page, total):
    d.line((MARGIN, H - 112, W - MARGIN, H - 112), fill=LINE, width=2)
    f = font(REGULAR_FONTS, 28)
    d.text((MARGIN, H - 90), HANDLE, font=f, fill=SOFT)
    label = f"{page} / {total}"
    d.text((W - MARGIN - d.textlength(label, font=f), H - 90), label, font=f, fill=SOFT)


# ---------- 슬라이드 ----------

def cover(c, total, date_text):
    img = background((12, 17, 28), (30, 40, 62))
    d = ImageDraw.Draw(img)
    # 장식: 큰 원과 대각 띠
    d.ellipse((560, -260, 1340, 520), outline="#2A364F", width=3)
    d.ellipse((700, -120, 1200, 380), outline="#2A364F", width=3)
    d.polygon([(0, 700), (W, 520), (W, 560), (0, 740)], fill="#1B2538")
    d.rectangle((0, 0, 18, H), fill=YELLOW)

    pill(d, MARGIN, 80, "TODAY 사회 이슈", font(BLACK_FONTS, 34), YELLOW, INK)
    d.text((MARGIN, 160), date_text, font=font(REGULAR_FONTS, 32), fill=SOFT)

    tf = font(BLACK_FONTS, 90)
    mw = W - MARGIN * 2
    sub_f = font(BOLD_FONTS, 42)
    th = text_height(d, c["cover_title"], tf, mw, 20)
    sh = text_height(d, c["cover_sub"], sub_f, mw, 10)
    y = H - 190 - sh - 40 - th
    y = draw_text(d, c["cover_title"], tf, MARGIN, y, mw, WHITE, 20, last_fill=YELLOW)
    draw_text(d, c["cover_sub"], sub_f, MARGIN, y + 36, mw, SOFT, 10)
    d.text((MARGIN, H - 112), "옆으로 넘겨서 확인  →", font=font(BOLD_FONTS, 32), fill=YELLOW)
    f = font(REGULAR_FONTS, 28)
    label = f"1 / {total}"
    d.text((W - MARGIN - d.textlength(label, font=f), H - 110), label, font=f, fill=SOFT)
    return img


def body(item, num, page, total):
    img = background()
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 18, H), fill=YELLOW)
    # 큰 번호 워터마크
    d.text((W - 60 - d.textlength(f"{num:02d}", font=font(BLACK_FONTS, 300)), 40), f"{num:02d}",
           font=font(BLACK_FONTS, 300), fill="#1E2A40")

    label = (item.get("label") or "").strip() or (SLIDE_LABELS[num - 1] if num <= len(SLIDE_LABELS) else f"POINT {num}")
    pill(d, MARGIN, 90, label, font(BLACK_FONTS, 32), YELLOW, INK)
    mw = W - MARGIN * 2
    tf, bf = font(BLACK_FONTS, 72), font(REGULAR_FONTS, 50)
    block = text_height(d, item["title"], tf, mw, 16) + 90 + text_height(d, item["body"], bf, mw, 26)
    top = 320 + max(0, (H - 112 - 320 - block) // 2 - 40)      # 글 덩어리를 가운데로
    y = draw_text(d, item["title"], tf, MARGIN, top, mw, WHITE, 16)
    d.rounded_rectangle((MARGIN, y + 30, MARGIN + 120, y + 40), 5, fill=YELLOW)
    draw_highlighted(d, item["body"], item.get("highlight"), bf, MARGIN, y + 90, mw, 26)
    footer(d, page, total)
    return img


def closing(outlets, page, total):
    img = background((12, 17, 28), (30, 40, 62))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 18, H), fill=YELLOW)
    mw = W - MARGIN * 2

    names = ", ".join(outlets[:5]) if outlets else "주요 언론사"
    src_f, note_f = font(BOLD_FONTS, 54), font(REGULAR_FONTS, 40)
    note = "이 계정은 뉴스를 요약·정리해 전달해요. 정확한 내용은 각 언론사의 원문 기사를 확인해 주세요."
    block = (40 + 24 + text_height(d, f"{names} 등 보도 종합", src_f, mw, 16) + 100
             + text_height(d, note, note_f, mw, 18) + 130 + 100)
    y = max(150, (H - 112 - block) // 2)
    d.text((MARGIN, y), "출처", font=font(BLACK_FONTS, 40), fill=YELLOW)
    y = draw_text(d, f"{names} 등 보도 종합", src_f, MARGIN, y + 64, mw, WHITE, 16)
    d.line((MARGIN, y + 50, W - MARGIN, y + 50), fill=LINE, width=2)
    y = draw_text(d, note, note_f, MARGIN, y + 90, mw, SOFT, 18)
    pill(d, MARGIN, y + 90, "팔로우하고 매일 받아보기", font(BLACK_FONTS, 46), YELLOW, INK, 48, 22)
    footer(d, page, total)
    return img


def render_all(content: dict, outlets: list, date_text: str, out_dir: Path) -> list:
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(content["slides"]) + 2
    images = [cover(content, total, date_text)]
    for i, s in enumerate(content["slides"], 1):
        images.append(body(s, i, i + 1, total))
    images.append(closing(outlets, total, total))
    paths = []
    for i, im in enumerate(images, 1):
        p = out_dir / f"{i:02d}.jpg"
        im.convert("RGB").save(p, "JPEG", quality=92)
        paths.append(p)
    return paths


if __name__ == "__main__":
    import json
    import sys

    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(render_all(data, ["연합뉴스", "KBS", "한겨레"], "2026.10.17 (토)", Path(sys.argv[2])))
