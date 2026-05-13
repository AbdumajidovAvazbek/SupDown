import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_service import analyze
from database import Video, get_db, init_db
from subtitle_service import get_subtitles


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="SupDown", lifespan=lifespan)


class ExtractRequest(BaseModel):
    url: str
    lang: str = "en"


@app.post("/api/extract")
async def extract(req: ExtractRequest, db: AsyncSession = Depends(get_db)):
    try:
        data = await get_subtitles(req.url, req.lang)
    except Exception as e:
        raise HTTPException(400, str(e))

    result = await db.execute(select(Video).where(Video.video_id == data["video_id"]))
    video = result.scalar_one_or_none()

    if video:
        video.subtitles = data["subtitles"]
        video.language = data["language"]
        video.title = data["title"]
    else:
        video = Video(
            url=req.url,
            video_id=data["video_id"],
            title=data["title"],
            subtitles=data["subtitles"],
            language=data["language"],
        )
        db.add(video)

    await db.commit()
    await db.refresh(video)
    return _detail(video)


@app.get("/api/videos")
async def list_videos(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Video).order_by(desc(Video.created_at)).limit(100)
    )
    return [_summary(v) for v in result.scalars()]


@app.get("/api/videos/{vid}")
async def get_video(vid: int, db: AsyncSession = Depends(get_db)):
    return _detail(await _or_404(vid, db))


@app.post("/api/analyze/{vid}")
async def run_analysis(vid: int, db: AsyncSession = Depends(get_db)):
    video = await _or_404(vid, db)
    if not video.subtitles:
        raise HTTPException(400, "Subtitrlar yo'q")
    try:
        video.ai_analysis = await analyze(video.title or "", video.subtitles)
        await db.commit()
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"ai_analysis": video.ai_analysis}


@app.get("/api/download/{vid}")
async def download(vid: int, db: AsyncSession = Depends(get_db)):
    video = await _or_404(vid, db)
    parts = [
        f"Title: {video.title}",
        f"URL: {video.url}",
        "",
        "=" * 50,
        "",
        "SUBTITLES:",
        "",
        video.subtitles or "",
    ]
    if video.ai_analysis:
        parts += ["", "=" * 50, "", "AI TAHLILI:", "", video.ai_analysis]
    return PlainTextResponse(
        "\n".join(parts),
        headers={
            "Content-Disposition": f'attachment; filename="{video.video_id}.txt"'
        },
    )


@app.delete("/api/videos/{vid}")
async def delete_video(vid: int, db: AsyncSession = Depends(get_db)):
    video = await _or_404(vid, db)
    await db.delete(video)
    await db.commit()
    return {"ok": True}


@app.get("/api/health")
async def health():
    return {"status": "ok"}


async def _or_404(vid: int, db: AsyncSession) -> Video:
    result = await db.execute(select(Video).where(Video.id == vid))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(404, "Video topilmadi")
    return video


def _summary(v: Video) -> dict:
    return {
        "id": v.id,
        "video_id": v.video_id,
        "title": v.title,
        "language": v.language,
        "has_analysis": v.ai_analysis is not None,
        "created_at": str(v.created_at),
    }


def _detail(v: Video) -> dict:
    return {**_summary(v), "subtitles": v.subtitles, "ai_analysis": v.ai_analysis}


FRONTEND_DIR = os.environ.get("FRONTEND_DIR", "/app/frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
