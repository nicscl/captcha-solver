import base64
import os

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.environ.get("IMAGE_MODEL", "google/gemini-2.5-flash")

PROMPT = (
    "You are an OCR system. Extract the exact text shown in this CAPTCHA image. "
    "Respond with ONLY the text — no punctuation, no explanation, no markdown."
)


def solve(image_bytes: bytes, content_type: str = "image/jpeg") -> str:
    api_key = os.environ["OPENROUTER_API_KEY"]
    b64 = base64.b64encode(image_bytes).decode()
    payload = {
        "model": MODEL,
        "temperature": 0.0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{content_type};base64,{b64}"},
                    },
                ],
            }
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    r = httpx.post(OPENROUTER_URL, json=payload, headers=headers, timeout=60.0)
    r.raise_for_status()
    data = r.json()
    if "choices" not in data:
        raise RuntimeError(f"no choices in response: {data}")
    return data["choices"][0]["message"]["content"].strip()
