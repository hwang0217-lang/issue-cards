"""Gemini 이미지 모델로 기사의 핵심 대상(동물·사물·날씨 등)이 보이는 배경 이미지를 만든다. 키가 없거나 실패하면 None.

뉴스 계정이라 사람, 실제 사건·사고 현장, 글자·로고가 나오는 이미지는 만들지 않는다 (오해 방지).
"""
import base64
import io
import os
import time

from PIL import Image

MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-nano-banana-2.1")
SIZE = os.environ.get("GEMINI_IMAGE_SIZE", "1K")  # 대문자 K만 허용돼요
ASPECT = "4:5"  # 카드뉴스 1080x1350과 같은 비율

RULES = (
    "High-quality editorial photograph, natural vivid colors, crisp detail, the main subject clearly visible "
    "and prominent in the frame, dramatic but natural lighting. "
    "Keep the top 25 percent and the bottom 30 percent of the frame fairly calm so text can be placed there. "
    "Strictly no people, no faces, no hands, no crowds, no text, no letters, no numbers, no signs, no logos, "
    "no flags, no brand names, no license plates, no identifiable real landmarks, "
    "and do not depict disasters, accidents, injuries, blood, violence or protests."
)


def build_prompt(subject: str, style: str = "") -> str:
    parts = [subject.strip().rstrip("."), style.strip().rstrip("."), RULES]
    return ". ".join(p for p in parts if p)


def generate_image(subject: str, style: str = ""):
    key = os.environ.get("GEMINI_API_KEY")
    if not key or not subject:
        return None
    try:
        from google import genai
    except ImportError:
        print("google-genai가 설치되지 않았어요")
        return None

    client = genai.Client(api_key=key)
    prompt = build_prompt(subject, style)
    for attempt in range(3):
        try:
            interaction = client.interactions.create(
                model=MODEL,
                input=prompt,
                response_format={"type": "image", "aspect_ratio": ASPECT, "image_size": SIZE},
            )
            data = interaction.output_image.data
            raw = base64.b64decode(data) if isinstance(data, str) else data
            return Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception as e:
            print(f"이미지 생성 실패 {attempt + 1}/3 ({subject[:40]}): {e}")
            time.sleep(4 * (attempt + 1))
    return None
