"""Client OpenAI (hoặc endpoint tương thích qua OPENAI_BASE_URL)."""
import base64
import io
import json
import re
from functools import lru_cache

from app import config


def enabled() -> bool:
    return bool(config.OPENAI_API_KEY and config.LLM_MODEL)


@lru_cache
def client():
    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)


def _json_from(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    return json.loads(m.group(0)) if m else {}


async def chat(messages: list[dict], tools: list | None = None):
    kw = {"model": config.LLM_MODEL, "messages": messages}
    if tools:
        kw["tools"] = tools
    resp = await client().chat.completions.create(**kw)
    return resp.choices[0].message


async def complete_text(system: str, user: str) -> str:
    msg = await chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
    return (msg.content or "").strip()


def _small_jpeg(image_path: str, side: int = 1024) -> str:
    """Ảnh camera điện thoại vài MB -> 1024px: gửi nhanh hơn, mô hình đọc nhanh hơn, đủ chi tiết."""
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
    im.thumbnail((side, side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


async def vision_json(prompt: str, image_path: str, effort: str | None = None) -> dict:
    kw = {"reasoning_effort": effort} if effort else {}
    resp = await client().chat.completions.create(
        model=config.VISION_MODEL, **kw,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_small_jpeg(image_path)}"}},
        ]}],
    )
    return _json_from(resp.choices[0].message.content)
