import json
from pathlib import Path

import yaml

from conftest import FakeRunner
from igdm_digest.cli import main
from igdm_digest.pipeline import load_last_run, run_pipeline


def test_end_to_end_with_file_delivery(export_dir, cfg, fake_runner, fixed_now):
    run = run_pipeline(cfg, export_path=export_dir, runner=fake_runner, now=fixed_now)
    s = run["stats"]
    assert run["my_name"] == "나"
    assert s["threads_total"] == 4 and s["analyzed"] == 3 and s["errors"] == 0
    assert s["new_messages"] == 4 and s["skipped_old"] == 2  # 오래된 메시지 + 반응 메시지
    cats = {i["sender"]: i["analysis"]["category"] for i in run["items"]}
    assert cats == {"김정보": "useful", "박강의": "funnel", "최요청": "noise"}
    # funnel 로 분류된 DM 의 액션 제안은 저장하지 않는다
    assert [a["title"] for a in run["actions"]] == ["해외 Shopify 스토어 오픈 체크리스트 실행", "펜션 홈페이지 제작 제안 메일"]
    assert all(a["status"] == "proposed" for a in run["actions"])
    assert "파일 저장" in run["delivery"]
    md = run["markdown"]
    assert "쇼피파이 해외 판매 체크리스트 — 김정보 (2026-09-30)" in md and "igdm approve" in md
    assert "무료 특강 유도 — 박강의" in md
    assert s["tokens"]["calls"] == 3 and s["tokens"]["input_tokens"] == 300

    data = Path(cfg["paths"]["data_dir"])
    state = json.loads((data / "state.json").read_text(encoding="utf-8"))
    assert len(state["seen_message_ids"]) == 6 and state["runs"][0]["analyzed"] == 3
    assert len(json.loads((data / "actions.json").read_text(encoding="utf-8"))) == 2
    assert load_last_run(cfg)["stats"]["analyzed"] == 3
    assert "본문" not in fake_runner.prompts[0] or "<link" not in fake_runner.prompts[0]  # fetch_links=False

    # 두 번째 실행: 새 메시지가 없으므로 분석하지 않는다
    run2 = run_pipeline(cfg, export_path=export_dir, runner=FakeRunner(), now=fixed_now)
    assert run2["stats"]["analyzed"] == 0 and run2["stats"]["new_messages"] == 0
    assert "유익한 DM 이 없었습니다" in run2["markdown"]


def test_auto_execute_and_limit(export_dir, cfg, fake_runner, fixed_now):
    cfg["actions"]["auto_execute"] = ["checklist"]
    run = run_pipeline(cfg, export_path=export_dir, runner=fake_runner, now=fixed_now, deliver=False)
    done = [a for a in run["actions"] if a["status"] == "done"]
    assert [a["type"] for a in done] == ["checklist"] and Path(done[0]["result_path"]).exists()
    assert next(a for a in run["actions"] if a["type"] == "outreach_email")["status"] == "proposed"
    assert "자동 실행된 액션" in run["markdown"] and run["delivery"].startswith("전달 생략")

    # limit: 상한을 넘는 대화방은 다음 실행으로 미룬다 (seen 처리하지 않음)
    cfg2 = json.loads(json.dumps(cfg))
    cfg2["paths"]["data_dir"] = cfg["paths"]["data_dir"] + "_2"
    cfg2["actions"]["auto_execute"] = []
    r1 = run_pipeline(cfg2, export_path=export_dir, runner=FakeRunner(), now=fixed_now, deliver=False, limit=1)
    assert r1["stats"]["analyzed"] == 1 and r1["stats"]["deferred"] == 2
    r2 = run_pipeline(cfg2, export_path=export_dir, runner=FakeRunner(), now=fixed_now, deliver=False)
    assert r2["stats"]["analyzed"] == 2


def test_analysis_error_keeps_message_unseen(export_dir, cfg, fixed_now):
    class Flaky(FakeRunner):
        def structured(self, system, user, schema, **kw):
            if 'sender="김정보"' in user:
                from igdm_digest.analyze import ClaudeError
                raise ClaudeError("timeout")
            return super().structured(system, user, schema, **kw)

    run = run_pipeline(cfg, export_path=export_dir, runner=Flaky(), now=fixed_now, deliver=False)
    assert run["stats"]["errors"] == 1 and run["errors"][0]["sender"] == "김정보"
    run2 = run_pipeline(cfg, export_path=export_dir, runner=FakeRunner(), now=fixed_now, deliver=False)
    assert run2["stats"]["analyzed"] == 1 and run2["items"][0]["sender"] == "김정보"


def test_delivery_failure_falls_back_to_file(export_dir, cfg, fixed_now, monkeypatch):
    cfg["delivery"]["method"] = "gmail"
    cfg["delivery"]["gmail"].update({"from": "me@gmail.com"})
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    run = run_pipeline(cfg, export_path=export_dir, runner=FakeRunner(), now=fixed_now)
    assert run["delivery"].startswith("전달 실패") and "파일로 저장" in run["delivery"]
    assert list((Path(cfg["paths"]["data_dir"]) / "reports").glob("digest-*.md"))


def test_dry_run_changes_nothing(export_dir, cfg, fixed_now):
    run = run_pipeline(cfg, export_path=export_dir, dry_run=True, now=fixed_now)
    assert [p["sender"] for p in run["preview"]] == ["최요청", "박강의", "김정보"]
    assert not (Path(cfg["paths"]["data_dir"]) / "state.json").exists()


def test_cli_dry_run_and_actions(export_dir, cfg, tmp_path, capsys):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    assert main(["--config", str(cfg_path), "run", "--export", str(export_dir), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "[미리보기] 내 이름: 나" in out and "김정보" in out
    assert main(["--config", str(cfg_path), "actions"]) == 0
    assert "액션이 없습니다" in capsys.readouterr().out
    assert main(["--config", str(cfg_path), "run"]) == 2
    assert main(["--config", str(tmp_path / "missing.yaml"), "actions"]) == 2
