"""레퍼런스 영상 수집: 선택된 릴스를 내려받아 장면 전환(컷) 기준으로 잘라 저장.

폴더 구조: <root>/<키워드>/<영상제목>_<code>/{원본.mp4, cut_001.mp4, ..., info.json}
컷 감지는 PySceneDetect(ContentDetector) + ffmpeg 재인코딩(프레임 정확).
"""
from __future__ import annotations

import json
import re
import subprocess
import urllib.request
from pathlib import Path


def safe_title(caption: str, code: str, max_len: int = 30) -> str:
    text = (caption or "").split("\n")[0]
    text = text.split("#")[0]
    text = re.sub(r"[^\w\s가-힣ㄱ-ㅎㅏ-ㅣ.,!?~()-]", "", text)  # 이모지·특수문자 제거
    text = re.sub(r"[\\/:*?\"<>|]", "", text)  # 파일명 금지문자 (Windows 포함)
    text = re.sub(r"\s+", " ", text).strip(" .")[:max_len].strip(" .")
    return f"{text}_{code}" if text else code


def download(url: str, dest: Path, timeout: int = 120) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=timeout) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 16):
            f.write(chunk)
    return dest


def detect_cuts(video: Path, threshold: float = 27.0, min_scene_len: int = 12) -> list[tuple[float, float]]:
    from scenedetect import ContentDetector, detect

    scenes = detect(str(video), ContentDetector(threshold=threshold, min_scene_len=min_scene_len))
    if not scenes:
        return []
    return [(s.get_seconds(), e.get_seconds()) for s, e in scenes]


def split(video: Path, scenes: list[tuple[float, float]], out_dir: Path) -> list[dict]:
    cuts = []
    for n, (start, end) in enumerate(scenes, 1):
        dest = out_dir / f"cut_{n:03d}.mp4"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-i", str(video), "-t", f"{end - start:.3f}",
             "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
             "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(dest)],
            check=True,
        )
        cuts.append({"file": dest.name, "start_s": round(start, 3), "end_s": round(end, 3), "duration_s": round(end - start, 3)})
    return cuts


def collect_one(item: dict, keyword: str, root: Path) -> Path:
    """item: code, video_url, caption, user, plays, duration (+ 선택 메타)."""
    folder = root / keyword / safe_title(item.get("caption", ""), item["code"])
    folder.mkdir(parents=True, exist_ok=True)
    original = folder / "원본.mp4"
    if not original.exists() or original.stat().st_size == 0:
        download(item["video_url"], original)
    scenes = detect_cuts(original)
    for old in folder.glob("cut_*.mp4"):
        old.unlink()
    cuts = split(original, scenes, folder) if len(scenes) > 1 else []
    info = {
        "keyword": keyword,
        "search_query": item.get("query"),
        "code": item["code"],
        "url": f"https://www.instagram.com/reel/{item['code']}/",
        "author": item.get("user"),
        "caption": item.get("caption"),
        "plays": item.get("plays"),
        "duration_s": item.get("duration"),
        "selection": item.get("selection"),
        "cuts": cuts or [{"file": "원본.mp4", "note": "컷 전환 없음(단일 샷)"}],
        "note": "연출 참고용 수집. 원저작자 동의 없이 재게시·상업적 사용 금지.",
    }
    (folder / "info.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return folder
