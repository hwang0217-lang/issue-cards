"""Gemini 이미지 모델로 기사 분위기에 맞는 '일반적인 배경 이미지'를 만든다. 키가 없거나 실패하면 None.

뉴스 계정이라 실제 사건 현장처럼 보이는 사진은 만들지 않는다 (오해 방지).
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
    "Generic editorial stock-style photograph that symbolizes the topic, atmospheric and calm, "
    "muted dark color grading with soft contrast and plenty of empty space for text overlay. "
    "Strictly no people, no faces, no hands, no text, no letters, no numbers, no signs, no logos, no flags, "
    "no real landmarks or identifiable buildings, no license plates, "
    "and do not depict disasters, accidents, injuries, violence, protests or crowds. "
    "It must look like a generic mood image, not a photo of a real news event."
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
