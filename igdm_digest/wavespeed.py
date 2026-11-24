"""WaveSpeed API: 파일 업로드 → 예측(prediction) 제출 → 폴링 → 결과 다운로드.

키는 환경변수 WAVESPEED_API_KEY (Authorization: Bearer).
문서: https://wavespeed.ai/docs/upload-files-api , 모델별 https://wavespeed.ai/models/<model>
"""
from __future__ import annotations

import json
import mimetypes
import os
import time
import urllib.request
from pathlib import Path

API = "https://api.wavespeed.ai/api/v3"
KLING_FLASH_R2V = "kwaivgi/kling-v4.0-flash/reference-to-video"


class WaveSpeedError(RuntimeError):
    pass


def _key() -> str:
    k = os.environ.get("WAVESPEED_API_KEY")
    if not k:
        raise WaveSpeedError("WAVESPEED_API_KEY 환경변수가 없습니다.")
    return k


def _call(method: str, url: str, body: dict | None = None, timeout: int = 60) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise WaveSpeedError(f"{method} {url} → HTTP {e.code}: {e.read()[:500]!r}") from e
    if out.get("code") not in (200, None):
        raise WaveSpeedError(f"{method} {url} → {out}")
    return out.get("data", out)


def balance() -> float:
    return float(_call("GET", f"{API}/balance")["balance"])


def upload(path: Path) -> str:
    """파일을 WaveSpeed 저장소에 올리고 모델 입력용 download_url 을 돌려준다."""
    size = path.stat().st_size
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    ticket = _call("POST", f"{API}/media/uploads", {"filename": path.name, "size": size, "content_type": ctype})
    up = ticket["upload"]
    req = urllib.request.Request(up["url"], data=path.read_bytes(), method=up.get("method", "PUT"),
                                 headers=up.get("headers") or {})
    with urllib.request.urlopen(req, timeout=300) as r:
        if r.status >= 300:
            raise WaveSpeedError(f"업로드 실패: HTTP {r.status}")
    return ticket["download_url"]


def submit(model: str, payload: dict) -> str:
    data = _call("POST", f"{API}/{model}", payload)
    pid = data.get("id")
    if not pid:
        raise WaveSpeedError(f"prediction id 없음: {data}")
    return pid


def wait(pid: str, timeout_s: int = 1800, every: float = 3.0) -> dict:
    t0 = time.time()
    while True:
        data = _call("GET", f"{API}/predictions/{pid}/result")
        status = data.get("status")
        if status == "completed":
            return data
        if status in ("failed", "canceled", "cancelled"):
            raise WaveSpeedError(f"생성 실패: {data.get('error') or data}")
        if time.time() - t0 > timeout_s:
            raise WaveSpeedError(f"시간 초과({timeout_s}s): 마지막 상태 {status}")
        time.sleep(every)
        every = min(every * 1.3, 15)


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=300) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 16):
            f.write(chunk)
    return dest


def kling_flash_r2v(prompt: str, *, videos: list[str] = (), images: list[str] = (), duration: int = 5,
                    aspect_ratio: str = "auto", keep_original_sound: bool = False) -> dict:
    if not 3 <= duration <= 20:
        raise WaveSpeedError("duration 은 3~20초")
    payload = {"prompt": prompt, "duration": int(duration), "aspect_ratio": aspect_ratio,
               "keep_original_sound": keep_original_sound}
    if videos:
        payload["videos"] = list(videos)
    if images:
        payload["images"] = list(images)
    pid = submit(KLING_FLASH_R2V, payload)
    res = wait(pid)
    res["prediction_id"] = pid
    return res
