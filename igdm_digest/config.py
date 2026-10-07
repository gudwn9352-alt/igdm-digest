"""설정 로딩: config.yaml 을 기본값과 깊은 병합(deep merge) 한다."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {
    "instagram": {
        "my_name": "",
        "include_message_requests": True,
        "timezone": "Asia/Seoul",
    },
    "analysis": {
        "model": "claude-opus-5-5",
        "effort": "high",
        "fetch_links": True,
        "max_link_chars": 6000,
        "min_usefulness_to_report": 40,
        "server_side_fallbacks": True,
        # 처음 실행 시 수년치 DM 을 전부 분석하지 않도록 기간을 제한한다 (0 = 제한 없음)
        "since_days": 60,
        # 한 번의 실행에서 분석할 최대 대화방 수 (비용 상한). 나머지는 다음 실행에서 처리된다.
        "max_threads_per_run": 50,
        # 새 메시지 앞뒤 맥락으로 함께 보여줄 이전 메시지 수
        "context_messages": 10,
    },
    "business": {"owner": "", "summary": "", "goals": {"this_week": "", "ongoing": ""}, "lines": [], "constraints": ""},
    "delivery": {
        "method": "stdout",
        "subject_prefix": "[IG DM 다이제스트]",
        "gmail": {
            "to": "",
            "from": "",
            "app_password_env": "GMAIL_APP_PASSWORD",
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
        },
        "file": {"dir": "data/reports"},
    },
    "actions": {
        "auto_execute": [],
        "outreach_from_name": "",
        "outreach_signature": "",
    },
    "paths": {"data_dir": "data"},
}


def deep_merge(base: dict, override: dict | None) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_config(path: str | Path | None = "config.yaml", *, required: bool = False) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    if path is None:
        return cfg
    p = Path(path)
    if not p.exists():
        if required:
            raise FileNotFoundError(
                f"설정 파일이 없습니다: {p} (config.example.yaml 을 config.yaml 로 복사해 채우세요)"
            )
        return cfg
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"설정 파일 형식이 잘못되었습니다: {p}")
    return deep_merge(cfg, data)


def data_dir(cfg: dict) -> Path:
    d = Path(cfg["paths"]["data_dir"]).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    return d
