"""Higgsfield API: 업로드 → 제출 → 폴링 → 다운로드.

인증: Authorization: Key KEY_ID:KEY_SECRET (환경변수 HF_KEY="KEY_ID:KEY_SECRET").
문서: https://docs.higgsfield.ai/docs (requests, polling, file-uploads)
가격(2026-11-24 모델 문서): kling-video/v4.0-flash/reference-to-video 720p
  - 참고 영상 없음: $0.094/출력초
  - 참고 영상 있음: $0.063 × (출력초 + max(참고영상 총길이, 출력초))  → 참고 영상은 출력 길이에 맞춰 자를 것
"""
from __future__ import annotations

import json
import mimetypes
import os
import random
import time
import urllib.request
from pathlib import Path

API = "https://api.higgsfield.ai"
KLING_FLASH_R2V = "kling-video/v4.0-flash/reference-to-video"
KLING_IMAGE_EDIT = "kling-image/v4.0/edit"
TERMINAL = {"completed", "failed", "nsfw", "canceled"}


class HiggsfieldError(RuntimeError):
    pass


def _key() -> str:
    k = os.environ.get("HF_KEY")
    if not k:
        raise HiggsfieldError("HF_KEY 환경변수(KEY_ID:KEY_SECRET)가 없습니다.")
    return k


def _call(method: str, url: str, body: dict | None = None, timeout: int = 60, idem: str | None = None) -> dict:
    headers = {"Authorization": f"Key {_key()}", "Content-Type": "application/json"}
    if idem:
        headers["Idempotency-Key"] = idem
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise HiggsfieldError(f"{method} {url} → HTTP {e.code}: {e.read()[:600]!r}") from e


def upload(path: Path) -> str:
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if ctype == "image/jpg":
        ctype = "image/jpeg"
    t = _call("POST", f"{API}/files/generate-upload-url", {"content_type": ctype})
    req = urllib.request.Request(t["upload_url"], data=path.read_bytes(), method="PUT", headers=t.get("upload_headers") or {"Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=300) as r:
        if r.status >= 300:
            raise HiggsfieldError(f"업로드 실패 HTTP {r.status}")
    return t["public_url"]


def submit(model: str, payload: dict, idem: str | None = None) -> dict:
    return _call("POST", f"{API}/{model}", payload, idem=idem)


def wait(sub: dict, timeout_s: int = 1800) -> dict:
    url = sub.get("status_url") or f"{API}/requests/{sub['request_id']}/status"
    t0, delay = time.time(), 2.0
    while True:
        try:
            res = _call("GET", url, timeout=30)
        except HiggsfieldError as e:
            if "HTTP 5" not in str(e):
                raise
            res = {"status": "retry"}
        st = res.get("status")
        if st in TERMINAL:
            if st != "completed":
                raise HiggsfieldError(f"생성 {st}: {res.get('error') or res}")
            return res
        if time.time() - t0 > timeout_s:
            raise HiggsfieldError(f"시간 초과: 마지막 상태 {st}")
        time.sleep(delay + random.uniform(0, 0.5))
        delay = min(delay * 1.5, 10.0)


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=300) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 16):
            f.write(chunk)
    return dest


def output_url(res: dict) -> str:
    if res.get("video"):
        return res["video"]["url"]
    if res.get("images"):
        return res["images"][0]["url"]
    raise HiggsfieldError(f"출력 URL 없음: {res}")


def kling_flash_r2v(prompt: str, *, video_urls=(), image_urls=(), duration: int = 5, aspect_ratio: str = "9:16", idem=None) -> dict:
    if not 3 <= duration <= 20:
        raise HiggsfieldError("duration 은 3~20초")
    body = {"prompt": prompt, "duration": int(duration), "resolution": "720p", "aspect_ratio": aspect_ratio}
    if video_urls:
        body["video_urls"] = list(video_urls)
    if image_urls:
        body["image_urls"] = list(image_urls)
    return wait(submit(KLING_FLASH_R2V, body, idem=idem))


def kling_image_edit(prompt: str, image_urls, *, aspect_ratio: str = "9:16", resolution: str = "2k", idem=None) -> dict:
    body = {"prompt": prompt, "image_urls": list(image_urls), "aspect_ratio": aspect_ratio, "resolution": resolution}
    return wait(submit(KLING_IMAGE_EDIT, body, idem=idem))
