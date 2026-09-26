import json
from pathlib import Path

import pytest

from paper_audit import SPECIALISTS, audit_paper, load_paper, split_sections

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
HALLUCINATED = FIXTURES / "hallucinated.pdf"
HUMAN = FIXTURES / "human.pdf"

ISSUE_KEYS = {"issue_type", "claim_text", "evidence_span", "jev_label", "reason"}
ISSUE_TYPES = {"citation", "number", "dataset", "test", "support"}
HIDDEN_SENTENCE = "Probe below 0.60 AUC on the holdout. AI-likeness hidden."


def _collecting_recorder() -> tuple[list[tuple[str, str, str, str]], object]:
    calls: list[tuple[str, str, str, str]] = []

    def recorder(job_id: str, specialist: str, state: str, detail: str) -> None:
        calls.append((job_id, specialist, state, detail))

    return calls, recorder


def _issue_types(result: dict) -> list[str]:
    return [issue["issue_type"] for issue in result["issues"]]


def _write_pdf(path: Path, text: str) -> Path:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(
        fitz.Rect(72, 72, 540, 720),
        text,
        fontsize=11,
        fontname="helv",
    )
    doc.save(path)
    doc.close()
    return path


def test_load_paper_includes_both_titles() -> None:
    hallucinated = load_paper(HALLUCINATED)
    human = load_paper(HUMAN)
    assert "Reported Accuracy on a Public Benchmark" in hallucinated
    assert "Measured Accuracy on a Public Benchmark" in human


def test_load_paper_does_not_use_http(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("load_paper must not use HTTP")

    monkeypatch.setattr("httpx.Client", boom)
    load_paper(HUMAN)


def test_split_sections_has_required_keys() -> None:
    sections = split_sections(load_paper(HALLUCINATED))
    for key in ("abstract", "introduction", "methods", "results", "references", "other"):
        assert key in sections
    assert "95.2" in sections["abstract"]
    assert "61.0" in sections["results"]
    assert "Smith" not in sections["references"]
    assert "2099" not in sections["references"]


def test_split_sections_human_keeps_lee_in_references() -> None:
    sections = split_sections(load_paper(HUMAN))
    assert "61.0" in sections["abstract"]
    assert "61.0" in sections["results"]
    assert "Lee, 2020" in sections["references"]


def test_split_sections_no_headings_is_weak_other() -> None:
    text = "Just a blob of paper text with no structure at all."
    sections = split_sections(text)
    for key in ("abstract", "introduction", "methods", "results", "references", "other"):
        assert key in sections
    assert sections["other"] == text
    assert sections["abstract"] == ""
    assert sections["section_quality"] == "weak"


def test_audit_records_started_then_finished_for_each_specialist() -> None:
    calls, recorder = _collecting_recorder()
    result = audit_paper(HUMAN, "job-1", recorder=recorder)
    expected: list[tuple[str, str, str]] = []
    for name in SPECIALISTS:
        expected.append(("job-1", name, "started"))
        expected.append(("job-1", name, "finished"))
    assert SPECIALISTS == [
        "parse",
        "claims",
        "evidence",
        "citations",
        "numbers",
        "tables",
        "dataset",
        "reproduce",
        "verify",
        "critic",
        "stamp",
    ]
    assert [(job_id, name, state) for job_id, name, state, _detail in calls] == expected
    assert [(event["specialist"], event["state"]) for event in result["events"]] == [
        (name, state) for _job_id, name, state in expected
    ]


def test_default_recorder_is_shelf_record_event(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, str]] = []

    def fake_record(job_id: str, specialist: str, state: str, detail: str) -> None:
        calls.append((job_id, specialist, state))

    monkeypatch.setattr("shelf.record_event", fake_record)
    result = audit_paper(HUMAN, "job-shelf")
    assert calls[0] == ("job-shelf", "parse", "started")
    assert ("job-shelf", "stamp", "finished") in calls
    assert result["events"]


def test_hallucinated_flags_citation_and_number() -> None:
    _calls, recorder = _collecting_recorder()
    result = audit_paper(HALLUCINATED, "job-h", recorder=recorder)
    types = _issue_types(result)
    assert "citation" in types
    assert "number" in types
    citation = next(issue for issue in result["issues"] if issue["issue_type"] == "citation")
    assert "Smith" in citation["claim_text"] or "Smith" in citation["evidence_span"]
    assert "2099" in citation["claim_text"] or "2099" in citation["evidence_span"]
    number = next(issue for issue in result["issues"] if issue["issue_type"] == "number")
    assert "95.2" in number["claim_text"] or "95.2" in number["evidence_span"]


def test_human_does_not_flag_lee_or_matching_number() -> None:
    _calls, recorder = _collecting_recorder()
    result = audit_paper(HUMAN, "job-human", recorder=recorder)
    types = _issue_types(result)
    assert "citation" not in types
    assert "number" not in types
    assert "support" not in types
    assert "dataset" not in types
    joined = " ".join(
        f"{issue['claim_text']} {issue['evidence_span']}" for issue in result["issues"]
    )
    assert "Lee, 2020" not in joined or "citation" not in types


def test_human_accuracy_sentence_is_not_support_issue() -> None:
    _calls, recorder = _collecting_recorder()
    result = audit_paper(HUMAN, "job-support", recorder=recorder)
    for issue in result["issues"]:
        if issue["issue_type"] == "support":
            assert "Accuracy reached 61.0%" not in issue["claim_text"]


def test_support_flags_when_no_shared_content_word(tmp_path: Path) -> None:
    path = _write_pdf(
        tmp_path / "gap.pdf",
        "Support Gap Paper\n\n"
        "Abstract\n"
        "Quantum flux exceeded seventeen units on the public benchmark (Lee, 2020).\n\n"
        "Methods\n"
        "We used a linear probe.\n\n"
        "Results\n"
        "The model score was 12.\n\n"
        "References\n"
        "Lee, 2020. A measured study.\n",
    )
    _calls, recorder = _collecting_recorder()
    result = audit_paper(path, "job-gap", recorder=recorder)
    assert "support" in _issue_types(result)


def test_issue_schema_and_jev_labels() -> None:
    _calls, recorder = _collecting_recorder()
    result = audit_paper(HALLUCINATED, "job-jev", recorder=recorder)
    assert result["issues"]
    for issue in result["issues"]:
        assert set(issue) >= ISSUE_KEYS
        assert issue["issue_type"] in ISSUE_TYPES
        assert issue["jev_label"] == "contradicted"
        assert issue["reason"].strip()
        assert "\n" not in issue["reason"].strip()
        assert "fraudulent" not in issue["reason"].lower()


def test_resolve_finished_detail_says_a_citation_does_not_resolve() -> None:
    calls, recorder = _collecting_recorder()
    result = audit_paper(HALLUCINATED, "job-resolve", recorder=recorder)
    details = [
        detail
        for _job_id, name, state, detail in calls
        if name == "citations" and state == "finished"
    ]
    assert details
    assert "does not resolve" in details[0].lower()
    assert "fraudulent" not in details[0].lower()
    assert "written by ai" not in details[0].lower()
    citation = next(issue for issue in result["issues"] if issue["issue_type"] == "citation")
    assert isinstance(citation["page"], int)
    assert citation["page"] >= 1


def test_repeated_citation_is_one_issue(tmp_path: Path) -> None:
    path = _write_pdf(
        tmp_path / "repeat.pdf",
        "Repeat Paper\n\n"
        "Abstract\n"
        "Accuracy reached 95.2% on the public benchmark (Smith, 2099).\n"
        "A later sentence cites the same missing source (Smith, 2099).\n\n"
        "Methods\n"
        "We fit a linear probe.\n\n"
        "Results\n"
        "The model score was 12.\n\n"
        "References\n"
        "Lee, 2020. A measured study.\n",
    )
    _calls, recorder = _collecting_recorder()
    result = audit_paper(path, "job-repeat", recorder=recorder)
    citations = [issue for issue in result["issues"] if issue["issue_type"] == "citation"]
    assert len(citations) == 1
    assert "Smith, 2099" in citations[0]["evidence_span"]


def test_failed_citation_stays_in_issue_list() -> None:
    _calls, recorder = _collecting_recorder()
    result = audit_paper(HALLUCINATED, "job-keep", recorder=recorder)
    citations = [issue for issue in result["issues"] if issue["issue_type"] == "citation"]
    assert citations
    assert any("Smith" in (issue["claim_text"] + issue["evidence_span"]) for issue in citations)


def test_ai_likeness_never_creates_an_issue() -> None:
    _calls, recorder = _collecting_recorder()
    result = audit_paper(HUMAN, "job-ai", recorder=recorder, auc=0.99)
    assert all(issue["issue_type"] in ISSUE_TYPES for issue in result["issues"])
    assert all(issue["issue_type"] != "ai_likeness" for issue in result["issues"])
    assert "ai-likeness" not in " ".join(issue["reason"].lower() for issue in result["issues"])


def test_provenance_hides_below_threshold_and_adds_no_issue() -> None:
    _calls, recorder = _collecting_recorder()
    result = audit_paper(HUMAN, "job-hide", recorder=recorder, auc=0.59)
    assert result["hidden"] is True
    assert HIDDEN_SENTENCE in result.values() or any(
        value == HIDDEN_SENTENCE for value in result.values()
    )
    assert "provenance" not in _issue_types(result)
    assert all(issue["issue_type"] != "ai_likeness" for issue in result["issues"])


def test_provenance_visible_when_auc_at_threshold() -> None:
    _calls, recorder = _collecting_recorder()
    result = audit_paper(HUMAN, "job-visible", recorder=recorder, auc=0.60)
    assert result["hidden"] is False


def test_provenance_uses_probe_should_hide(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[float] = []

    def fake_hide(auc: float) -> bool:
        seen.append(auc)
        return True

    monkeypatch.setattr("probe.should_hide", fake_hide)
    _calls, recorder = _collecting_recorder()
    result = audit_paper(HUMAN, "job-probe", recorder=recorder, auc=0.41)
    assert seen == [0.41]
    assert result["hidden"] is True
    assert HIDDEN_SENTENCE in str(result)


def test_dataset_issue_when_named_dataset_missing(tmp_path: Path) -> None:
    path = _write_pdf(
        tmp_path / "dataset.pdf",
        "Dataset Miss Paper\n\n"
        "Abstract\n"
        "Accuracy reached 61.0% on missing-owner/missing-set (Lee, 2020).\n\n"
        "Results\n"
        "The model accuracy was 61.0%.\n\n"
        "References\n"
        "Lee, 2020.\n",
    )
    text = load_paper(path)
    from paper_audit import dataset_issues

    issues = dataset_issues(
        [{"text": "We report accuracy on secret-lab/hidden-csv.", "dataset": "secret-lab/hidden-csv"}],
        text,
    )
    assert issues
    assert issues[0]["issue_type"] == "dataset"
    _calls, recorder = _collecting_recorder()
    fixture_result = audit_paper(HUMAN, "job-ds", recorder=recorder)
    assert "dataset" not in _issue_types(fixture_result)


def test_kaggle_runner_reads_results_file_without_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {
        "where": "kaggle",
        "status": "match",
        "log": "passed 4 tests",
        "kernel_url": "https://www.kaggle.com/code/example/claim",
    }
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(payload), encoding="utf-8")

    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("kaggle_runner must not shell out")

    monkeypatch.setattr("subprocess.run", boom)
    monkeypatch.setattr("subprocess.call", boom)
    monkeypatch.setattr("subprocess.Popen", boom)
    monkeypatch.setattr("os.system", boom)

    _calls, recorder = _collecting_recorder()
    result = audit_paper(HUMAN, "job-kaggle", results_path=results_path, recorder=recorder)
    assert result["kaggle"]["where"] == "kaggle"
    assert result["kaggle"]["status"] == "match"
    assert result["kaggle"]["log"] == "passed 4 tests"
    assert result["kaggle"]["kernel_url"] == payload["kernel_url"]
    assert "test" not in _issue_types(result)


def test_kaggle_runner_missing_file_is_not_run() -> None:
    _calls, recorder = _collecting_recorder()
    result = audit_paper(HUMAN, "job-norun", results_path=None, recorder=recorder)
    assert result["kaggle"]["status"] == "not_run"
    detail = str(result["kaggle"].get("detail") or result["kaggle"].get("log") or "")
    assert "results file" in detail.lower() or "no results" in detail.lower()
    assert "test" not in _issue_types(result)


def test_claim_without_dataset_slug_is_not_run() -> None:
    _calls, recorder = _collecting_recorder()
    result = audit_paper(HUMAN, "job-slug", recorder=recorder)
    assert result["kaggle"]["status"] == "not_run"


def test_kaggle_mismatch_emits_test_issue(tmp_path: Path) -> None:
    payload = {
        "where": "local",
        "status": "mismatch",
        "log": "assert 0.50 == 0.90",
        "kernel_url": None,
    }
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(payload), encoding="utf-8")
    _calls, recorder = _collecting_recorder()
    result = audit_paper(HUMAN, "job-mismatch", results_path=results_path, recorder=recorder)
    assert "test" in _issue_types(result)


def test_repro_results_attach_to_the_dataset_claim() -> None:
    demo = FIXTURES / "demo_paper.pdf"

    def repro(claims: list[dict], _sections: dict) -> list[dict]:
        target = next(claim for claim in claims if "317" in str(claim.get("text") or ""))
        return [
            {
                "claim_id": target["claim_id"],
                "dataset_slug": "yasserh/titanic-dataset",
                "resolution": "match",
                "spec": {"operation": "COUNT_EQ", "column": "Pclass", "equals": 1},
                "actual": 216,
                "expected": 317,
                "status": "could_not_reproduce",
                "steps": ["Executed COUNT_EQ"],
                "log": "computed 216, claimed 317",
                "formula": "COUNT_EQ(Pclass, 1)",
            }
        ]

    result = audit_paper(demo, "job-attach", repro=repro)
    claim = next(item for item in result["claims"] if "317" in str(item.get("text") or ""))
    assert claim["verdict"] == "could_not_reproduce"
    assert claim["computation"]["actual"] == 216
    assert claim["computation"]["formula"] == "COUNT_EQ(Pclass, 1)"


def test_audit_does_not_call_openrouter_or_xai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("paper audit must stay offline")

    monkeypatch.setattr("httpx.Client", boom)
    monkeypatch.setattr("httpx.AsyncClient", boom)
    try:
        import jev

        monkeypatch.setattr(jev, "judge_claim", boom)
    except ImportError:
        pass
    _calls, recorder = _collecting_recorder()
    audit_paper(HALLUCINATED, "job-offline", recorder=recorder)
