"""Apify 'data-slayer/instagram-search-reels' Actor 로 키워드 릴스 검색.

Actor 는 Apify 서버에서 실행되고(인스타그램 로그인 불필요), 비용은 Apify 계정에 청구된다.
가격(2026-11-24 Apify API 기준): 실행 시작 $0.002 + 결과 1건당 $0.0025(무료 플랜).
토큰은 환경변수 APIFY_TOKEN 에서 읽는다.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

ACTOR_ID = "data-slayer/instagram-search-reels"


class ReelsError(RuntimeError):
    pass


def _get(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def search_reels(query: str, *, max_pages: int = 1, max_charge_usd: float = 0.5, token: str | None = None, client=None) -> list[dict]:
    """키워드로 릴스를 검색해 결과(dict 목록)를 돌려준다."""
    if not query.strip():
        raise ReelsError("검색어가 비어 있습니다.")
    if not 1 <= max_pages <= 100:
        raise ReelsError("max_pages 는 1~100 이어야 합니다.")
    if client is None:
        token = token or os.environ.get("APIFY_TOKEN")
        if not token:
            raise ReelsError("APIFY_TOKEN 환경변수가 없습니다. Apify 콘솔 → Settings → API & Integrations 에서 토큰을 발급해 설정하세요.")
        from apify_client import ApifyClient

        client = ApifyClient(token)
    run = client.actor(ACTOR_ID).call(
        run_input={"query": query, "maxPages": max_pages},
        max_total_charge_usd=Decimal(str(max_charge_usd)),
    )
    if run is None:
        raise ReelsError("Actor 실행 결과를 받지 못했습니다.")
    status = _get(run, "status")
    status = getattr(status, "value", status)
    if status != "SUCCEEDED":
        raise ReelsError(f"Actor 실행 실패: 상태 {status}")
    dataset_id = _get(run, "default_dataset_id") or _get(run, "defaultDatasetId")
    return list(client.dataset(dataset_id).iterate_items())


def summarize(item: dict) -> dict:
    """결과 한 건에서 자주 쓰는 항목만 뽑는다(필드가 없으면 빈 값)."""
    def pick(*keys):
        for k in keys:
            cur: Any = item
            for part in k.split("."):
                cur = cur.get(part) if isinstance(cur, dict) else None
            if cur not in (None, ""):
                return cur
        return None

    caption = pick("caption.text", "caption")
    return {
        "url": pick("url", "permalink") or (f"https://www.instagram.com/reel/{item['code']}/" if item.get("code") else None),
        "user": pick("user.username", "owner.username", "username"),
        "plays": pick("play_count", "ig_play_count", "playCount", "video_play_count"),
        "likes": pick("like_count", "likeCount"),
        "comments": pick("comment_count", "commentCount"),
        "caption": caption[:200] if isinstance(caption, str) else caption,
    }


def save_results(items: list[dict], out_dir: Path, query: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in query)[:40]
    path = out_dir / f"reels-{safe}-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
