"""번인(burned-in) 자막 제거: OCR 글자 검출로 '큰 글줄'만 골라 인페인팅.

참고 영상을 AI 영상 모델(Kling reference-to-video 등)에 넣을 때 자막이 따라 그려지지 않게 하는 전처리.
- RapidOCR 의 검출(det) 모델만 사용 (글자 인식 불필요, 한국어 모델 다운로드 불필요)
- 자막 판정: 글줄 높이가 화면 높이의 min_line_h 이상 (화이트보드·간판 같은 작은 글씨 제외)
- 앞뒤 프레임 검출을 합쳐(temporal) 깜빡임 없이 지움
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import cv2
import numpy as np

_engine = None


def _ocr():
    global _engine
    if _engine is None:
        import logging

        from rapidocr import RapidOCR

        logging.getLogger("RapidOCR").setLevel(logging.WARNING)
        _engine = RapidOCR()
    return _engine


def detect_lines(frame: np.ndarray) -> list[np.ndarray]:
    r = _ocr()(frame, use_det=True, use_cls=False, use_rec=False)
    boxes = getattr(r, "boxes", None)
    return [] if boxes is None else [np.asarray(b, dtype=np.float32) for b in boxes]


def subtitle_boxes(frame: np.ndarray, min_line_h: float = 0.02, max_center_offset: float = 0.15, min_bright: float = 0.07,
                   bright_v: int = 235, band: tuple[float, float] = (0.08, 0.92)) -> list[np.ndarray]:
    """자막 글줄 판정: 큰 글자 + 화면 가로 중앙 + 박스 안에 아주 밝은(흰) 글자 픽셀이 충분히 있음.

    화이트보드·종이의 손글씨는 '흰 바탕에 어두운 글씨'라 밝은 픽셀 비율이 거의 0 이므로 걸러진다.
    """
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    out = []
    for b in detect_lines(frame):
        ys, xs = b[:, 1], b[:, 0]
        x0, x1, y0, y1 = int(max(xs.min(), 0)), int(min(xs.max(), w)), int(max(ys.min(), 0)), int(min(ys.max(), h))
        if x1 - x0 < w * 0.08 or y1 - y0 < h * min_line_h:
            continue
        cy, cx = (y0 + y1) / 2 / h, (x0 + x1) / 2 / w
        if not (band[0] <= cy <= band[1]) or abs(cx - 0.5) > max_center_offset:
            continue
        if (gray[y0:y1, x0:x1] >= bright_v).mean() < min_bright:
            continue
        out.append(b)
    return out


def boxes_to_mask(shape, boxes, pad: int = 10) -> np.ndarray:
    m = np.zeros(shape[:2], np.uint8)
    for b in boxes:
        cv2.fillPoly(m, [b.astype(np.int32)], 255)
    if pad:
        m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_RECT, (pad * 2 + 1, pad * 2 + 1)))
    return m


def scan_subtitles(video: Path, every: int = 3, **kw) -> dict:
    """영상에 자막 형태(크고·가운데·흰 글자)의 글줄이 있는지 검사. 생성 결과 검수용."""
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    hits, checked, i = [], 0, 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if i % every == 0:
            checked += 1
            boxes = subtitle_boxes(f, **kw)
            if boxes:
                hits.append(round(i / fps, 2))
        i += 1
    cap.release()
    return {"frames_checked": checked, "frames_with_subtitle_like_text": len(hits), "times_s": hits[:50]}


def remove_subtitles(src: Path, dst: Path, *, window: int = 2, **kw) -> dict:
    """src 영상의 자막을 지워 dst 로 저장. 처리한 프레임 수 등 통계를 돌려준다."""
    cap = cv2.VideoCapture(str(src))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    cap.release()
    if not frames:
        raise ValueError(f"프레임을 읽지 못했습니다: {src}")
    h, w = frames[0].shape[:2]
    masks = [boxes_to_mask(f.shape, subtitle_boxes(f, **kw)) for f in frames]
    tmp = dst.with_suffix(".noaudio.mp4")
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p", str(tmp)],
        stdin=subprocess.PIPE,
    )
    touched = 0
    for i, f in enumerate(frames):
        m = np.zeros((h, w), np.uint8)
        for j in range(max(0, i - window), min(len(frames), i + window + 1)):
            m |= masks[j]
        if m.any():
            touched += 1
            f = cv2.inpaint(f, m, 7, cv2.INPAINT_TELEA)
        proc.stdin.write(f.tobytes())
    proc.stdin.close()
    proc.wait()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp), "-i", str(src), "-map", "0:v", "-map", "1:a?", "-c", "copy",
                    "-shortest", str(dst)], check=True)
    tmp.unlink()
    return {"frames": len(frames), "frames_inpainted": touched}
