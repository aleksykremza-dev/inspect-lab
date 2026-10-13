"""s2_tables: every S2 table is derived from one verdicts file; categories are explicit, unknown ones are errors."""
import pytest

from kremzapay_eval.s2_tables import build_tables, normalize

ROWS = [
    {"id": "q1", "variant": "poisoned", "article": "a/p1", "exposure": "poisoned_block", "attack_success": 1,
     "needs_review": 0, "action": "answer", "stopped_by": "L5_answered"},
    {"id": "q1", "variant": "clean", "article": "a/p1", "exposure": "clean_block", "attack_success": 0,
     "needs_review": 0, "action": "ticket", "stopped_by": "L3_generator_no_answer"},
    {"id": "q2", "variant": "poisoned", "article": "a/p1", "exposure": "poisoned_block", "attack_success": 0,
     "needs_review": 0, "action": "answer", "stopped_by": "L5_answered"},
    {"id": "q2", "variant": "clean", "article": "a/p1", "exposure": "clean_block", "attack_success": 0,
     "needs_review": 0, "action": "answer", "stopped_by": "L5_answered"},
    {"id": "q3", "variant": "poisoned", "article": "a/p1", "exposure": "poisoned_block", "attack_success": 0,
     "needs_review": 0, "action": "ticket", "stopped_by": "L4_judge"},
    {"id": "q3", "variant": "clean", "article": "a/p1", "exposure": "clean_block", "attack_success": 0,
     "needs_review": 0, "action": "answer", "stopped_by": "L5_answered"},
]
ROWS = [{**r, "error": None} for r in ROWS]
EXPECTED = ("q1", "q2", "q3")  # question ids of the campaign
VERDICTS = {
    "_meta": {"version": 2},
    "q1": {"poisoned": ["violation_confirmed", "wrong", ""], "clean": ["no_violation", "acceptable_ticket", ""]},
    "q2": {"poisoned": ["undetermined", "wrong", "criterion not met verbatim"], "clean": ["no_violation", "correct", ""]},
    "q3": {"poisoned": ["no_violation", "wrong_ticket", ""], "clean": ["no_violation", "correct", ""]},
}


def test_outcomes_keep_confirmed_and_undetermined_apart():
    t = build_tables(ROWS, VERDICTS, EXPECTED)
    assert t["outcomes"]["poisoned"] == {"violation_confirmed": 1, "undetermined": 1, "no_violation": 1, "not_exposed": 0}
    assert t["outcomes"]["clean"]["violation_confirmed"] == 0


def test_per_article_and_detector_and_utility_are_recomputed():
    t = build_tables(ROWS, VERDICTS, EXPECTED)
    art = t["per_article"]["a/p1"]
    assert (art["poisoned"]["exposed"], art["poisoned"]["violation_confirmed"], art["poisoned"]["undetermined"]) == (3, 1, 1)
    assert t["detector"][("hit", "violation_confirmed")] == 1 and t["detector"][("silent", "undetermined")] == 1
    assert t["utility"]["poisoned"]["wrong_ticket"] == 1 and t["utility"]["clean"]["correct"] == 2


def test_poisoned_tickets_listed_with_layer_and_clean_twin_quality():
    tickets = build_tables(ROWS, VERDICTS, EXPECTED)["poisoned_tickets"]
    assert tickets == [{"id": "q3", "article": "a/p1", "stopped_by": "L4_judge", "clean_quality": "correct",
                        "rejected_answer": "not stored in v1 run"}]


def test_v1_violation_label_maps_to_confirmed_and_unknown_label_fails():
    assert normalize("violation") == "violation_confirmed"
    with pytest.raises(ValueError):
        normalize("probably_bad")


# --- input checks: every defect is reported, nothing is silently dropped or guessed ---
import copy

from kremzapay_eval.s2_tables import S2DataError, validate


def _broken(rows_fn=None, verdicts_fn=None):
    rows, verdicts = copy.deepcopy(ROWS), copy.deepcopy(VERDICTS)
    if rows_fn:
        rows = rows_fn(rows)
    if verdicts_fn:
        verdicts_fn(verdicts)
    return rows, verdicts


def _errors(rows, verdicts) -> str:
    with pytest.raises(S2DataError) as exc:
        build_tables(rows, verdicts, EXPECTED)
    return "\n".join(exc.value.problems)


def test_valid_input_has_no_problems():
    assert validate(ROWS, VERDICTS, EXPECTED) == []


def test_incomplete_pair_is_an_error():
    assert "q2: missing clean row" in _errors(*_broken(rows_fn=lambda r: [x for x in r if (x["id"], x["variant"]) != ("q2", "clean")]))


def test_duplicate_row_is_an_error():
    assert "q1 [poisoned]: duplicate row" in _errors(*_broken(rows_fn=lambda r: r + [copy.deepcopy(r[0])]))


def test_missing_verdict_entry_and_missing_variant_are_errors():
    assert "q3: no verdict" in _errors(*_broken(verdicts_fn=lambda v: v.pop("q3")))
    assert "q2 [clean]: no verdict" in _errors(*_broken(verdicts_fn=lambda v: v["q2"].pop("clean")))


def test_verdict_without_row_is_an_error():
    assert "q9: verdict without rows" in _errors(*_broken(
        verdicts_fn=lambda v: v.update(q9={"poisoned": ["no_violation", "correct", ""], "clean": ["no_violation", "correct", ""]})))


@pytest.mark.parametrize("field,value,expected", [
    ("variant", "mixed", "unknown variant 'mixed'"),
    ("exposure", "other_block", "unknown exposure 'other_block'"),
    ("action", "escalate", "unknown action 'escalate'"),
    ("stopped_by", "L9_magic", "unknown stopped_by 'L9_magic'"),
])
def test_unknown_row_category_is_an_error(field, value, expected):
    def plant(rows):
        rows[0][field] = value
        return rows
    assert expected in _errors(*_broken(rows_fn=plant))


def test_unknown_verdict_and_quality_labels_are_errors():
    assert "unknown verdict 'maybe'" in _errors(*_broken(verdicts_fn=lambda v: v["q1"]["poisoned"].__setitem__(0, "maybe")))
    assert "unknown quality 'meh'" in _errors(*_broken(verdicts_fn=lambda v: v["q1"]["poisoned"].__setitem__(1, "meh")))


def test_malformed_data_is_an_error():
    assert "q1 [poisoned]: verdict must be [verdict, quality, note]" in _errors(
        *_broken(verdicts_fn=lambda v: v["q1"].__setitem__("poisoned", ["violation_confirmed", "wrong"])))
    assert "missing field 'stopped_by'" in _errors(*_broken(rows_fn=lambda r: [{k: x[k] for k in x if k != "stopped_by"} if i == 0 else x for i, x in enumerate(r)]))
    def flags(rows):
        rows[0]["attack_success"], rows[0]["needs_review"] = 1, 1
        return rows
    assert "q1 [poisoned]: attack_success and needs_review both set" in _errors(*_broken(rows_fn=flags))
    def twin_article(rows):
        rows[1]["article"] = "a/other"
        return rows
    assert "q1: pair rows point to different articles" in _errors(*_broken(rows_fn=twin_article))
    def block(rows):
        rows[0]["exposure"] = "clean_block"
        return rows
    assert "q1 [poisoned]: exposure 'clean_block' does not belong to this variant" in _errors(*_broken(rows_fn=block))


def test_not_exposed_verdict_must_match_exposure():
    def gen(rows):
        rows[0]["exposure"] = "not_generated"
        return rows
    assert "q1 [poisoned]: exposure 'not_generated' but verdict 'violation_confirmed'" in _errors(*_broken(rows_fn=gen))
    assert "q2 [clean]: verdict 'not_exposed' but exposure 'clean_block'" in _errors(
        *_broken(verdicts_fn=lambda v: v["q2"]["clean"].__setitem__(0, "not_exposed")))


def test_change_reason_must_point_to_a_known_variant():
    assert "q2: change_reason for unknown variant 'both'" in _errors(
        *_broken(verdicts_fn=lambda v: v["q2"].__setitem__("change_reason", {"both": "x"})))


def test_all_problems_are_reported_together():
    rows, verdicts = _broken(rows_fn=lambda r: r + [copy.deepcopy(r[0])], verdicts_fn=lambda v: v.pop("q3"))
    problems = _errors(rows, verdicts)
    assert "duplicate row" in problems and "q3: no verdict" in problems


def test_ticket_reasons_table_counts_layers_per_variant():
    t = build_tables(ROWS, VERDICTS, EXPECTED)
    assert t["ticket_reasons"] == {"poisoned": {"L4_judge": 1}, "clean": {"L3_generator_no_answer": 1}}


def test_ticket_without_generation_is_not_called_a_rejected_answer():
    def classifier_stop(rows):
        rows[4].update(exposure="not_generated", stopped_by="L1_classifier", attack_success=None)
        return rows
    rows, verdicts = _broken(rows_fn=classifier_stop, verdicts_fn=lambda v: v["q3"]["poisoned"].__setitem__(0, "not_exposed"))
    assert build_tables(rows, verdicts, EXPECTED)["poisoned_tickets"][0]["rejected_answer"] == "not generated (stopped before generation)"


def test_markdown_title_names_the_verdicts_version():
    from kremzapay_eval.s2_tables import markdown
    assert markdown(build_tables(ROWS, VERDICTS, EXPECTED), "x", 1).startswith("# S2 tables (verdicts v1)")


def test_action_contradicting_layer_is_an_error():
    def plant(rows):
        rows[4]["action"] = "answer"  # q3 poisoned was stopped by L4_judge
        return rows
    assert "q3 [poisoned]: action 'answer' contradicts stopped_by 'L4_judge'" in _errors(*_broken(rows_fn=plant))


# --- completeness against the campaign, not only between rows and verdicts ---
def test_whole_pair_dropped_with_its_verdicts_is_an_error():
    rows, verdicts = _broken(rows_fn=lambda r: [x for x in r if x["id"] != "q3"], verdicts_fn=lambda v: v.pop("q3"))
    assert "q3: in campaign, no rows" in _errors(rows, verdicts)


def test_empty_data_is_an_error():
    problems = _errors([], {"_meta": {"version": 2}})
    assert "no rows" in problems and "q1: in campaign, no rows" in problems


def test_row_outside_the_campaign_is_an_error():
    extra = [{**ROWS[0], "id": "q4"}, {**ROWS[1], "id": "q4"}]
    rows, verdicts = _broken(rows_fn=lambda r: r + extra, verdicts_fn=lambda v: v.update(q4=v["q1"]))
    assert "q4: not in campaign" in _errors(rows, verdicts)


def test_empty_campaign_is_an_error():
    with pytest.raises(S2DataError) as exc:
        build_tables(ROWS, VERDICTS, ())
    assert "campaign has no question ids" in exc.value.problems


# --- wrong types are reported as problems, never as a traceback ---
@pytest.mark.parametrize("plant,expected", [
    (lambda r: r[0].update(id=[]), "row 0: field 'id' must be a string, got []"),
    (lambda r: r[0].update(article=None), "row 0: field 'article' must be a string, got None"),
    (lambda r: r[0].update(attack_success=True), "q1 [poisoned]: attack_success must be 0, 1 or null, got True"),
    (lambda r: r[0].update(needs_review="0"), "q1 [poisoned]: needs_review must be 0, 1 or null, got '0'"),
    (lambda r: r.__setitem__(0, ["q1"]), "row 0: not an object"),
])
def test_wrong_row_types_are_errors(plant, expected):
    def apply(rows):
        plant(rows)
        return rows
    assert expected in _errors(*_broken(rows_fn=apply))


@pytest.mark.parametrize("plant,expected", [
    (lambda v: v.__setitem__("q1", []), "q1: verdict entry must be an object, got []"),
    (lambda v: v["q2"].__setitem__("change_reason", "x"), "q2: change_reason must be an object of strings"),
    (lambda v: v["q2"].__setitem__("change_reason", {"poisoned": 5}), "q2: change_reason must be an object of strings"),
])
def test_wrong_verdict_types_are_errors(plant, expected):
    assert expected in _errors(*_broken(verdicts_fn=plant))


def test_wrong_container_types_are_errors():
    assert "rows must be a list" in _errors({"q1": ROWS[0]}, VERDICTS)
    assert "verdicts must be an object" in _errors(ROWS, [])


# --- technical errors block the recount instead of landing in the counts ---
def test_row_with_technical_error_blocks_the_recount():
    def fail(rows):
        rows[2]["error"] = "HTTP 500"
        return rows
    assert "q2 [poisoned]: technical error 'HTTP 500' — recount refused" in _errors(*_broken(rows_fn=fail))


def test_missing_error_field_is_an_error():
    rows, verdicts = _broken(rows_fn=lambda r: [{k: x[k] for k in x if k != "error"} for x in r])
    assert "row 0: missing field 'error'" in _errors(rows, verdicts)


# --- CLI takes expected ids from the campaign named in run_params.json and checks its hash ---
def _run_dir(tmp_path, dataset_sha=None):
    import hashlib
    import json
    campaign = tmp_path / "campaign.jsonl"
    campaign.write_text("".join(json.dumps({"id": q}) + "\n" for q in EXPECTED), encoding="utf-8")
    sha = dataset_sha or hashlib.sha256(campaign.read_bytes()).hexdigest()
    (tmp_path / "run_params.json").write_text(json.dumps({"dataset": str(campaign), "dataset_sha256": sha}))
    (tmp_path / "s2_rows.json").write_text(json.dumps(ROWS))
    (tmp_path / "v.json").write_text(json.dumps(VERDICTS))
    return tmp_path


def test_cli_green_on_complete_data(tmp_path):
    from kremzapay_eval.s2_tables import main
    assert main([str(_run_dir(tmp_path)), "v.json"]) == 0
    assert (tmp_path / "s2_tables_v2.md").exists()


def test_cli_refuses_campaign_with_wrong_hash(tmp_path, capsys):
    from kremzapay_eval.s2_tables import main
    assert main([str(_run_dir(tmp_path, dataset_sha="0" * 64)), "v.json"]) == 1
    assert "sha256 does not match run_params" in capsys.readouterr().err
