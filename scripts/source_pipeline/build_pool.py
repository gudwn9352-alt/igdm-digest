"""Build candidate pool per folder keyword and contact sheets from Instagram scrubber sprites."""
import glob, io, json, os, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw

from pathlib import Path
DATA = str(Path(__file__).resolve().parents[2] / "data" / "reels")  # 저장소 기준
OUT = sys.argv[1]
GROUPS = {
    "부모님": ["부모님", "엄마아빠"],
    "부부": ["부부"],
    "일상": ["일상", "일상브이로그", "부부일상"],
    "장보기": ["장보기"],
    "병원": ["병원"],
    "공부": ["공부"],
    "재테크": ["재테크"],
}
EXCLUDE = {"DN1349e0hAk"}  # already collected in test? keep it eligible: remove from set below
EXCLUDE = set()


def latest(q):
    q = "".join(c if c.isalnum() else "_" for c in q)[:40]
    fs = [f for f in glob.glob(f"{DATA}/reels-{q}-*.json") if os.path.basename(f).startswith(f"reels-{q}-2")]
    return max(fs) if fs else None


seen = set()
pool = {}
for folder, qs in GROUPS.items():
    items = []
    for q in qs:
        f = latest(q)
        for it in json.load(open(f)) if f else []:
            code = it.get("code")
            if not code or code in seen or not it.get("video_url"):
                continue
            dur = it.get("video_duration") or 0
            if dur < 3 or dur > 90:
                continue
            seen.add(code)
            sp = ((it.get("image_versions") or {}).get("scrubber_spritesheet_info_candidates") or {}).get("default") or {}
            cap = ((it.get("caption") or {}).get("text") or "").replace("\n", " ")
            items.append({"code": code, "query": q, "duration": round(dur, 1), "plays": it.get("play_count"),
                          "user": (it.get("user") or {}).get("username"), "caption": cap[:300],
                          "video_url": it["video_url"], "sprite": sp})
    pool[folder] = items


def sheet(item, folder):
    sp = item["sprite"]
    path = f"{OUT}/sheets/{folder}/{item['code']}.jpg"
    if os.path.exists(path):
        return path
    try:
        urls = sp.get("sprite_urls") or []
        n_per = sp["total_thumbnail_num_per_sprite"]; per_row = sp["thumbnails_per_row"]
        tw, th = sp["thumbnail_width"], sp["thumbnail_height"]
        sprites = [Image.open(io.BytesIO(urllib.request.urlopen(u, timeout=30).read())).convert("RGB") for u in urls]
        total = sum(min(n_per, (s.width // tw) * (s.height // th)) for s in sprites)
        total = min(total, int(item["duration"] / sp["thumbnail_duration"]) + 1) if sp.get("thumbnail_duration") else total
        k = 12
        idxs = [round(i * (total - 1) / (k - 1)) for i in range(k)]
        canvas = Image.new("RGB", (tw * 2 * 6, th * 2 * 2), "black")
        d = ImageDraw.Draw(canvas)
        for j, idx in enumerate(idxs):
            s = sprites[idx // n_per]; r = idx % n_per
            x, y = (r % per_row) * tw, (r // per_row) * th
            thumb = s.crop((x, y, x + tw, y + th)).resize((tw * 2, th * 2))
            cx, cy = (j % 6) * tw * 2, (j // 6) * th * 2
            canvas.paste(thumb, (cx, cy))
            t = idx * sp.get("thumbnail_duration", 0)
            d.rectangle((cx, cy, cx + 44, cy + 14), fill="black"); d.text((cx + 2, cy + 1), f"{t:.1f}s", fill="yellow")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        canvas.save(path, quality=80)
        return path
    except Exception as e:  # noqa
        return f"ERR {e}"


jobs = [(it, f) for f, its in pool.items() for it in its]
with ThreadPoolExecutor(8) as ex:
    res = list(ex.map(lambda a: sheet(*a), jobs))
for (it, f), r in zip(jobs, res):
    it["sheet"] = r if not r.startswith("ERR") else None
    if r.startswith("ERR"):
        print(f, it["code"], r[:120])
for f in pool:
    pool[f] = [{k: v for k, v in it.items() if k != "sprite"} for it in pool[f] if it.get("sheet")]
    print(f, len(pool[f]))
json.dump(pool, open(f"{OUT}/pool.json", "w"), ensure_ascii=False, indent=1)
