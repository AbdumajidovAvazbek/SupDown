import asyncio
import re

import httpx
from youtube_transcript_api import TranscriptsDisabled, YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound

COOKIES_FILE = None  # reserved for future use


def _extract_video_id(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|embed/|v/)([a-zA-Z0-9_-]{11})", url)
    if not m:
        raise ValueError("Yaroqsiz YouTube URL")
    return m.group(1)


def _get_title(video_id: str) -> str:
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(
                "https://www.youtube.com/oembed",
                params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            )
            if r.status_code == 200:
                return r.json().get("title", video_id)
    except Exception:
        pass
    return video_id


def _dedup(lines: list[str]) -> str:
    result: list[str] = []
    for line in lines:
        if line and (not result or result[-1] != line):
            result.append(line)
    return "\n".join(result)


def _extract_sync(url: str, lang: str) -> dict:
    video_id = _extract_video_id(url)
    title    = _get_title(video_id)

    _api = YouTubeTranscriptApi()

    # Try direct fetch first (fastest path)
    fetched     = None
    actual_lang = lang
    langs_try   = list(dict.fromkeys([lang, "en"]))  # deduplicated, order preserved

    try:
        fetched     = _api.fetch(video_id, languages=langs_try)
        actual_lang = fetched.language_code
    except TranscriptsDisabled:
        raise ValueError("Bu videoda subtitrlar o'chirilgan")
    except Exception:
        # Fallback: list all languages, pick first available
        try:
            tlist = _api.list(video_id)
        except Exception as e:
            raise ValueError(f"YouTube ga ulanib bo'lmadi: {e}")

        transcript = None
        for candidate in langs_try:
            for finder in [
                tlist.find_manually_created_transcript,
                tlist.find_generated_transcript,
            ]:
                try:
                    transcript  = finder([candidate])
                    actual_lang = candidate
                    break
                except NoTranscriptFound:
                    pass
            if transcript:
                break

        if transcript is None:
            all_t = list(tlist)
            if not all_t:
                raise ValueError("Bu video uchun subtitrlar topilmadi")
            transcript  = all_t[0]
            actual_lang = transcript.language_code

        try:
            fetched = transcript.fetch()
        except Exception as e:
            raise ValueError(f"Subtitr yuklab bo'lmadi: {e}")

    # FetchedTranscript is iterable → snippets with .text attribute
    lines = [
        s.text.replace("\n", " ").strip()
        for s in fetched
        if s.text.strip()
    ]
    text = _dedup(lines)

    if not text.strip():
        raise ValueError("Subtitrlar bo'sh")

    return {
        "video_id": video_id,
        "title":    title,
        "subtitles": text,
        "language": actual_lang,
    }


async def get_subtitles(url: str, lang: str = "en") -> dict:
    return await asyncio.to_thread(_extract_sync, url, lang)
