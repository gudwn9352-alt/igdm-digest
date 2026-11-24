import json

import pytest

from igdm_digest import cli
from igdm_digest.reels import ACTOR_ID, ReelsError, save_results, search_reels, summarize

ITEMS = [{"code": "ABC", "user": {"username": "pension_kr"}, "play_count": 1200, "like_count": 30, "comment_count": 2, "caption": {"text": "펜션 홍보 팁"}}]


class FakeClient:
    def __init__(self, status="SUCCEEDED"):
        self.status, self.calls = status, []

    def actor(self, actor_id):
        self.calls.append(("actor", actor_id))
        return self

    def call(self, **kw):
        self.calls.append(("call", kw))
        return {"status": self.status, "defaultDatasetId": "ds1"}

    def dataset(self, ds_id):
        self.calls.append(("dataset", ds_id))
        return self

    def iterate_items(self):
        return iter(ITEMS)


def test_search_reels_passes_input_and_reads_dataset():
    fc = FakeClient()
    items = search_reels("펜션", max_pages=2, max_charge_usd=0.1, client=fc)
    assert items == ITEMS
    assert fc.calls[0] == ("actor", ACTOR_ID)
    assert fc.calls[1][1]["run_input"] == {"query": "펜션", "maxPages": 2}
    assert ("dataset", "ds1") in fc.calls


def test_search_reels_failed_run():
    with pytest.raises(ReelsError, match="FAILED"):
        search_reels("x", client=FakeClient("FAILED"))


def test_search_reels_requires_token(monkeypatch):
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    with pytest.raises(ReelsError, match="APIFY_TOKEN"):
        search_reels("x")


def test_summarize_and_save(tmp_path):
    s = summarize(ITEMS[0])
    assert s["url"] == "https://www.instagram.com/reel/ABC/"
    assert (s["user"], s["plays"], s["caption"]) == ("pension_kr", 1200, "펜션 홍보 팁")
    p = save_results(ITEMS, tmp_path, "펜션 홍보")
    assert json.loads(p.read_text(encoding="utf-8")) == ITEMS


def test_cli_reels(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("igdm_digest.reels.search_reels", lambda q, **kw: ITEMS)
    cfg_path = tmp_path / "c.yaml"
    cfg_path.write_text(f"paths:\n  data_dir: {tmp_path / 'data'}\n", encoding="utf-8")
    assert cli.main(["--config", str(cfg_path), "reels", "펜션"]) == 0
    out = capsys.readouterr().out
    assert "릴스 1건" in out and "pension_kr" in out
    assert list((tmp_path / "data" / "reels").glob("*.json"))
