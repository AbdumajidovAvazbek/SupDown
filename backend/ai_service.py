import os

import anthropic

_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
_client = anthropic.AsyncAnthropic(api_key=_api_key) if _api_key else None

_SYSTEM = """Siz foydali AI yordamchisiz. Foydalanuvchi YouTube videosining subtitrlarini beradi.
Foydalanuvchi ingliz tilini bilmaydi — javobni faqat O'ZBEK TILIDA yozing.

Javob markdown formatida bo'lsin:

## 📝 Mazmun
Video nima haqida — 2-3 ta jumla.

## 💡 Asosiy fikrlar
- Har bir muhim fikr bullet ko'rinishida

## 🚀 Amaliy maslahatlar
- Video aytgan foydali qadamlar yoki usullar

## 🧠 Qo'shimcha bilim (AI dan)
Video aytmagan lekin mavzu bilan bog'liq foydali ma'lumotlar va chuqurroq tushuntirish."""


async def analyze(title: str, subtitles: str) -> str:
    if not _client:
        raise ValueError("ANTHROPIC_API_KEY sozlanmagan. .env faylga qo'shing.")
    msg = await _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        system=[
            {
                "type": "text",
                "text": _SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": f"Video nomi: {title}\n\nSubtitrlar:\n{subtitles[:10000]}",
            }
        ],
    )
    return msg.content[0].text
