"""check_results: a run is complete only if it matches the expected campaign (ids, groups, dataset hash,
one consistent identity) and every planned sample was scored without error and none awaits review.
Logs come from real Inspect runs of the kremzapay task against the mock bot."""
import json
import os

import pytest
from inspect_ai import eval as inspect_eval, eval_set

from kremzapay_eval import bot_eval
from kremzapay_eval.check_results import EXIT_CODES, check, compare_samples, main
from kremzapay_eval.tests.mock_bot import serve_in_thread
from kremzapay_eval.tests.test_scorer_gates import RECORDS

CAMPAIGN_ID = "camp-1"


@pytest.fixture(scope="module")
def mock_url():
    server, url = serve_in_thread()
    yield url
    server.shutdown()


@pytest.fixture
def campaign(tmp_path):
    path = tmp_path / "campaign.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in RECORDS), encoding="utf-8")
    return path


def make_run(mode: str, url: str, log_dir, campaign, campaign_id=CAMPAIGN_ID, model="mockllm/model", **kwargs):
    os.environ["MOCK_MODE"] = mode
    task = bot_eval.kremzapay(attacks=str(campaign), phase="s1", bot_url=url, bot_db=str(log_dir / "none.db"),
                              campaign_id=campaign_id)
    inspect_eval(task, model=model, display="none", log_dir=str(log_dir), fail_on_error=False, **kwargs)


def checked(log_dir, campaign, campaign_id=CAMPAIGN_ID) -> dict:
    return check(log_dir, campaign, "s1", campaign_id)


def test_clean_run_is_complete(mock_url, tmp_path, campaign):
    make_run("safe", mock_url, tmp_path, campaign)
    result = checked(tmp_path, campaign)
    assert result["status"] == "complete", result["reasons"]
    assert (result["planned"], result["scored"], result["errored"]) == (5, 5, 0)
    assert result["attacks"] == {"determined": 3, "pending_review": 0, "successes": 0, "asr": 0.0, "families": 3}


def test_run_without_obs_is_incomplete_only_when_the_schema_is_required(mock_url, tmp_path, campaign):
    make_run("safe", mock_url, tmp_path, campaign)          # the mock bot records no turn_state, so no obs
    assert checked(tmp_path, campaign)["status"] == "complete"   # historical rule: obs not required
    result = check(tmp_path, campaign, "s1", CAMPAIGN_ID, obs_schema=1)
    assert result["status"] == "incomplete" and result["obs_schema"] == 1
    assert any("obs schema 1: 5 problem(s)" in r and "no obs record" in r for r in result["reasons"])


def test_unknown_obs_schema_is_a_reason():
    from kremzapay_eval.check_results import obs_problems
    assert obs_problems([], None) == [] and "unknown obs schema 7" in obs_problems([], 7)[0]


def test_pending_review_is_needs_review(mock_url, tmp_path, campaign):
    make_run("echo", mock_url, tmp_path, campaign)
    result = checked(tmp_path, campaign)
    assert result["status"] == "needs_review"
    assert result["attacks"]["determined"] == 2 and result["attacks"]["pending_review"] == 1


def test_errored_samples_are_incomplete(mock_url, tmp_path, campaign):
    make_run("error", mock_url, tmp_path, campaign)
    result = checked(tmp_path, campaign)
    assert result["status"] == "incomplete" and result["errored"] == 5


def test_empty_log_dir_is_incomplete(tmp_path, campaign):
    assert checked(tmp_path, campaign)["status"] == "incomplete"


def test_smoke_logs_in_subdir_are_ignored(mock_url, tmp_path, campaign):
    make_run("error", mock_url, tmp_path / "smoke", campaign)
    make_run("safe", mock_url, tmp_path, campaign)
    assert checked(tmp_path, campaign)["status"] == "complete"


def test_controls_only_campaign_is_incomplete(mock_url, tmp_path):
    controls = tmp_path / "controls.jsonl"
    controls.write_text("".join(json.dumps(r) + "\n" for r in RECORDS if r["group"] == "control"), encoding="utf-8")
    make_run("safe", mock_url, tmp_path, controls)
    result = checked(tmp_path, controls)
    assert result["status"] == "incomplete"
    assert any("no attack" in r for r in result["reasons"])


def test_other_dataset_than_expected_is_incomplete(mock_url, tmp_path, campaign):
    make_run("safe", mock_url, tmp_path, campaign)
    expected = tmp_path / "expected.jsonl"
    expected.write_text(campaign.read_text(encoding="utf-8") + json.dumps(
        {**RECORDS[2], "id": "atk-9", "canary": "kp-00000009.example"}) + "\n", encoding="utf-8")
    result = checked(tmp_path, expected)
    assert result["status"] == "incomplete"
    assert any("dataset" in r for r in result["reasons"]) and any("atk-9" in r for r in result["reasons"])


def test_partial_run_is_incomplete(mock_url, tmp_path, campaign):
    make_run("safe", mock_url, tmp_path, campaign, limit=3)
    result = checked(tmp_path, campaign)
    assert result["status"] == "incomplete" and any("missing" in r for r in result["reasons"])


def test_other_campaign_logs_are_ignored(mock_url, tmp_path, campaign):
    make_run("error", mock_url, tmp_path, campaign, campaign_id="camp-old")
    make_run("safe", mock_url, tmp_path, campaign)
    assert checked(tmp_path, campaign)["status"] == "complete"


def test_conflicting_runs_in_one_campaign_are_incomplete(mock_url, tmp_path, campaign):
    make_run("safe", mock_url, tmp_path, campaign)
    make_run("echo", mock_url, tmp_path, campaign, model="mockllm/other")
    result = checked(tmp_path, campaign)
    assert result["status"] == "incomplete" and any("conflicting" in r for r in result["reasons"])


def test_eval_set_retry_uses_the_successful_attempt(mock_url, tmp_path, campaign):
    os.environ.update(MOCK_MODE="flaky", MOCK_FLAKY_FAILS="2")
    task = bot_eval.kremzapay(attacks=str(campaign), phase="s1", bot_url=mock_url,
                              bot_db=str(tmp_path / "none.db"), campaign_id=CAMPAIGN_ID)
    ok, _ = eval_set(task, log_dir=str(tmp_path), model="mockllm/model", display="none", retry_attempts=2,
                     retry_wait=0.1, retry_cleanup=False)
    assert ok and len(list(tmp_path.glob("*.eval"))) == 2   # failed attempt kept on disk, then the retry
    assert checked(tmp_path, campaign)["status"] == "complete"


def test_compare_samples_reports_missing_extra_and_group_mismatch():
    expected = {"a": "attack", "b": "control", "c": "attack"}
    observed = {"a": "attack", "b": "attack", "d": "control"}
    reasons = compare_samples(expected, observed)
    assert any("missing" in r and "'c'" in r for r in reasons)
    assert any("unexpected" in r and "'d'" in r for r in reasons)
    assert any("group" in r and "'b'" in r for r in reasons)


@pytest.mark.parametrize("mode,status", [("safe", "complete"), ("echo", "needs_review"), ("error", "incomplete")])
def test_main_writes_status_json_and_exits_with_status_code(mock_url, tmp_path, monkeypatch, campaign, mode, status):
    make_run(mode, mock_url, tmp_path, campaign)
    monkeypatch.setattr("sys.argv", ["check_results.py", str(tmp_path), "--campaign", str(campaign),
                                     "--phase", "s1", "--campaign-id", CAMPAIGN_ID])
    assert main() == EXIT_CODES[status]
    assert json.loads((tmp_path / "status.json").read_text())["status"] == status
