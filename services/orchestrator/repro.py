"""Reproduction worker for one paper.

A claim is reproducible when it names a public Kaggle dataset and a table
check (row count, sum, mean, or a value count). The worker asks the model for
that check, falls back to a parser, runs the check on the CSV, and pushes the
same check as a Kaggle kernel when the CLI and keys are present.
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
DOWNLOADS = REPO_ROOT / "kaggle" / "downloads"
KERNEL_ID = "arxaudit/arxaudit-repro"
KERNEL_URL = f"https://www.kaggle.com/code/{KERNEL_ID}"
SLUG_RE = re.compile(r"\b([a-z0-9][a-z0-9_-]*/[a-z0-9][a-z0-9_-]*)\b", re.I)
OF_RE = re.compile(r"(\d+(?:\.\d+)?)\s+of\s+(\d+(?:\.\d+)?)", re.I)
COLUMN_RE = re.compile(r"column\s+`?([A-Za-z_][A-Za-z0-9_]*)`?", re.I)
EQ_RE = re.compile(
    r"`?([A-Za-z_][A-Za-z0-9_]*)`?\s*(?:=|equals|equal to)\s*`?([A-Za-z0-9.]+)`?",
    re.I,
)
SUM_RE = re.compile(
    r"sum of\s+`?([A-Za-z_][A-Za-z0-9_]*)`?\s+is\s+(\d+(?:\.\d+)?)",
    re.I,
)
MEAN_RE = re.compile(
    r"mean of\s+`?([A-Za-z_][A-Za-z0-9_]*)`?\s+is\s+(\d+(?:\.\d+)?)",
    re.I,
)
_SLUG_OK = re.compile(r"^[a-z0-9][a-z0-9_-]*/[a-z0-9][a-z0-9_-]*$")
_COLUMN_OK = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_OPS = {"rows", "sum", "mean", "count_eq"}
KNOWN_DATASETS = {"titanic": "yasserh/titanic-dataset"}

REPRO_PROMPT = """You are the reproduction worker for one paper.
Propose a table check only when the paper names a public Kaggle dataset as owner/name and states a count, sum, or mean on that table.
Reply with JSON only.
{"reproducible": true, "claim_text": "", "dataset_slug": "owner/name", "file_name": "table.csv", "checks": [{"op": "rows", "expected": 1}, {"op": "sum", "column": "Label", "expected": 1}, {"op": "mean", "column": "Score", "expected": 0.5}, {"op": "count_eq", "column": "Label", "equals": "1", "expected": 1}]}
If the written experiment needs a trained model, a private file, or no public table, reply {"reproducible": false, "reason": "short reason"}.
Do not write Python. Do not invent a dataset the paper does not name.
"""

Model = Callable[[str], str | None]
Pusher = Callable[[dict[str, Any]], dict[str, Any] | None]


def _not_run(detail: str, claim_text: str = "") -> dict[str, Any]:
    return {
        "where": "not_run",
        "status": "not_run",
        "log": "",
        "kernel_url": None,
        "detail": detail,
        "claim_text": claim_text,
        "code": "",
    }


def _number(value: str) -> int | float:
    if "." in value:
        return float(value)
    return int(value)


def _slug_in(text: str) -> str | None:
    match = SLUG_RE.search(text)
    if match:
        return match.group(1).lower()
    lowered = text.lower()
    if "kaggle" in lowered:
        for name, slug in KNOWN_DATASETS.items():
            if name in lowered:
                return slug
    return None


def _paper_blob(claims: list[dict[str, Any]], sections: dict[str, str]) -> str:
    parts = [
        sections.get("methods") or "",
        sections.get("results") or "",
        sections.get("abstract") or "",
    ]
    parts.extend(str(claim.get("text") or "") for claim in claims)
    return "\n".join(part for part in parts if part).strip()


def _heuristic(claims: list[dict[str, Any]], sections: dict[str, str]) -> dict[str, Any] | None:
    blob = _paper_blob(claims, sections)
    if not blob:
        return None
    for claim in claims:
        sentence = str(claim.get("text") or "").strip()
        if not sentence:
            continue
        window = f"{sentence}\n{sections.get('methods') or ''}"
        slug = claim.get("dataset") or _slug_in(window)
        if isinstance(slug, str):
            slug = slug.lower()
        if not slug or not _SLUG_OK.match(slug):
            continue
        checks: list[dict[str, Any]] = []
        counted = OF_RE.search(sentence)
        equal = EQ_RE.search(sentence)
        summed = SUM_RE.search(sentence)
        averaged = MEAN_RE.search(sentence)
        if counted and equal:
            checks.append({"op": "rows", "expected": _number(counted.group(2))})
            checks.append(
                {
                    "op": "count_eq",
                    "column": equal.group(1),
                    "equals": equal.group(2).rstrip("."),
                    "expected": _number(counted.group(1)),
                }
            )
        elif summed:
            checks.append(
                {
                    "op": "sum",
                    "column": summed.group(1),
                    "expected": _number(summed.group(2)),
                }
            )
        elif averaged:
            checks.append(
                {
                    "op": "mean",
                    "column": averaged.group(1),
                    "expected": _number(averaged.group(2)),
                }
            )
        elif counted and COLUMN_RE.search(sentence):
            checks.append({"op": "rows", "expected": _number(counted.group(2))})
        if not checks:
            continue
        spec = _clean_spec(
            {
                "reproducible": True,
                "claim_text": sentence,
                "dataset_slug": slug,
                "file_name": "",
                "checks": checks,
            }
        )
        if spec:
            return spec
    return None


def _clean_spec(raw: dict[str, Any]) -> dict[str, Any] | None:
    if raw.get("reproducible") is not True:
        return None
    slug = str(raw.get("dataset_slug") or "").strip().lower()
    if not _SLUG_OK.match(slug):
        return None
    claim_text = str(raw.get("claim_text") or "").strip()
    file_name = str(raw.get("file_name") or "").strip()
    if file_name and (Path(file_name).name != file_name or not file_name.lower().endswith(".csv")):
        return None
    checks_in = raw.get("checks")
    if not isinstance(checks_in, list) or not checks_in or len(checks_in) > 4:
        return None
    checks: list[dict[str, Any]] = []
    for item in checks_in:
        if not isinstance(item, dict):
            return None
        op = str(item.get("op") or "")
        if op not in _OPS:
            return None
        expected = item.get("expected")
        if isinstance(expected, bool) or not isinstance(expected, (int, float)):
            return None
        check: dict[str, Any] = {"op": op, "expected": expected}
        if op != "rows":
            column = str(item.get("column") or "")
            if not _COLUMN_OK.match(column):
                return None
            check["column"] = column
        if op == "count_eq":
            equals = str(item.get("equals") or "").strip()
            if not equals or len(equals) > 40:
                return None
            check["equals"] = equals
        checks.append(check)
    return {
        "claim_text": claim_text,
        "dataset_slug": slug,
        "file_name": file_name,
        "checks": checks,
    }


def _parse_model(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    body = text.strip()
    if body.startswith("```"):
        body = body.strip("`")
        body = body.removeprefix("json").strip()
    try:
        raw = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    return _clean_spec(raw)


def ask_model(prompt: str) -> str | None:
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        return None
    try:
        import httpx

        response = httpx.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": "grok-4.6",
                "messages": [
                    {"role": "system", "content": REPRO_PROMPT},
                    {"role": "user", "content": prompt[:6000]},
                ],
            },
            timeout=30,
        )
    except Exception:
        return None
    if response.status_code != 200:
        return None
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return content if isinstance(content, str) and content.strip() else None


def _with_dataset_sentences(
    claims: list[dict[str, Any]], sections: dict[str, str]
) -> list[dict[str, Any]]:
    extra = list(claims)
    seen = {str(claim.get("text") or "").strip() for claim in extra}
    for name in ("abstract", "methods", "results"):
        for sentence in re.split(r"(?<=[.!?])\s+", sections.get(name) or ""):
            cleaned = sentence.strip()
            slug = _slug_in(cleaned)
            if not slug or cleaned in seen:
                continue
            seen.add(cleaned)
            extra.append({"text": cleaned, "dataset": slug})
    return extra


def propose(
    claims: list[dict[str, Any]],
    sections: dict[str, str],
    model: Model | None = None,
) -> dict[str, Any] | None:
    expanded = _with_dataset_sentences(claims, sections)
    blob = _paper_blob(expanded, sections)
    if _slug_in(blob) is None and not any(claim.get("dataset") for claim in expanded):
        return None
    caller = model if model is not None else ask_model
    drafted = _parse_model(caller(blob[:6000]))
    if drafted:
        return drafted
    return _heuristic(expanded, sections)


def _kaggle_bin() -> str | None:
    sibling = Path(sys.executable).resolve().parent / "kaggle"
    if sibling.is_file():
        return str(sibling)
    return shutil.which("kaggle")


def find_table(slug: str, file_name: str) -> Path | None:
    roots = [DOWNLOADS, REPO_ROOT / "services" / "orchestrator" / ".arxiv-cache" / "datasets" / slug.replace("/", "__")]
    names = [file_name] if file_name else []
    for root in roots:
        if not root.is_dir():
            continue
        for name in names:
            candidate = root / name
            if candidate.is_file():
                return candidate
        found = sorted(root.glob("*.csv"))
        if len(found) == 1:
            return found[0]
        if file_name:
            continue
        titled = [path for path in found if slug.split("/")[-1].replace("-", "") in path.stem.lower().replace("-", "")]
        if len(titled) == 1:
            return titled[0]
    return None


def download_table(slug: str, file_name: str) -> Path | None:
    import datasets

    cached = datasets.lookup_table(slug)
    if cached is not None:
        return cached
    binary = _kaggle_bin()
    if not binary:
        return None
    if not os.environ.get("KAGGLE_USERNAME") or not os.environ.get("KAGGLE_KEY"):
        return None
    dest = REPO_ROOT / "services" / "orchestrator" / ".arxiv-cache" / "datasets" / slug.replace("/", "__")
    dest.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [binary, "datasets", "download", "-d", slug, "-p", str(dest), "--unzip"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        return None
    table = find_table(slug, file_name)
    if table is not None:
        datasets.remember_table(slug, table)
    return table


def _close(actual: float, expected: int | float) -> bool:
    if isinstance(expected, int) or float(expected).is_integer():
        return int(round(actual)) == int(expected)
    text = f"{expected}"
    places = len(text.split(".")[1]) if "." in text else 0
    return abs(actual - float(expected)) <= (10 ** (-places)) / 2 + 1e-9


def run_checks(path: Path, spec: dict[str, Any]) -> dict[str, Any]:
    claim_text = str(spec.get("claim_text") or "")
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except OSError:
        return {
            "status": "missing_row",
            "log": f"missing table {path.name}",
            "detail": "The public table could not be read.",
            "claim_text": claim_text,
        }
    if not rows:
        return {
            "status": "missing_row",
            "log": "table has no rows",
            "detail": "The public table has no rows.",
            "claim_text": claim_text,
        }
    lines: list[str] = []
    for check in spec["checks"]:
        op = check["op"]
        expected = check["expected"]
        if op == "rows":
            actual = len(rows)
            lines.append(f"rows {actual} expected {expected}")
            if not _close(actual, expected):
                return {
                    "status": "mismatch",
                    "log": "\n".join(lines),
                    "detail": f"The table has {actual} rows. The paper says {expected}.",
                    "claim_text": claim_text,
                }
            continue
        column = check["column"]
        if column not in rows[0]:
            return {
                "status": "missing_row",
                "log": f"missing column {column}",
                "detail": f"The table has no column {column}.",
                "claim_text": claim_text,
            }
        if op == "count_eq":
            equals = str(check["equals"])
            actual = sum(1 for row in rows if str(row.get(column) or "").strip() == equals)
            lines.append(f"count {column}={equals} {actual} expected {expected}")
        elif op == "sum":
            actual = sum(float(row[column]) for row in rows if str(row.get(column) or "").strip())
            lines.append(f"sum {column} {actual} expected {expected}")
        else:
            values = [float(row[column]) for row in rows if str(row.get(column) or "").strip()]
            actual = sum(values) / len(values) if values else 0
            lines.append(f"mean {column} {actual} expected {expected}")
        if not _close(float(actual), expected):
            return {
                "status": "mismatch",
                "log": "\n".join(lines),
                "detail": f"The {op} of {column} is {actual}. The paper says {expected}.",
                "claim_text": claim_text,
            }
    return {
        "status": "match",
        "log": "\n".join(lines),
        "detail": "The public table matches the count written in the paper.",
        "claim_text": claim_text,
    }


def notebook_code(spec: dict[str, Any], table: Path | None) -> str:
    target = str(table) if table else ""
    return (
        "import csv\n"
        f"path = {target!r}\n"
        f"checks = {spec['checks']!r}\n"
        "with open(path, newline='', encoding='utf-8') as handle:\n"
        "    rows = list(csv.DictReader(handle))\n"
        "print('rows', len(rows))\n"
        "for check in checks:\n"
        "    op = check['op']\n"
        "    expected = check['expected']\n"
        "    if op == 'rows':\n"
        "        print(op, len(rows), 'expected', expected)\n"
        "        continue\n"
        "    column = check['column']\n"
        "    if op == 'count_eq':\n"
        "        actual = sum(1 for row in rows if str(row.get(column) or '').strip() == str(check['equals']))\n"
        "    elif op == 'sum':\n"
        "        actual = sum(float(row[column]) for row in rows if str(row.get(column) or '').strip())\n"
        "    else:\n"
        "        values = [float(row[column]) for row in rows if str(row.get(column) or '').strip()]\n"
        "        actual = sum(values) / len(values)\n"
        "    print(op, column, actual, 'expected', expected)\n"
    )


def _kernel_source(spec: dict[str, Any]) -> str:
    payload = json.dumps(
        {
            "claim_text": spec["claim_text"],
            "dataset_slug": spec["dataset_slug"],
            "checks": spec["checks"],
        }
    )
    return f"""import csv, json
from pathlib import Path

SPEC = json.loads({payload!r})

def table():
    root = Path("/kaggle/input")
    if not root.exists():
        return None
    found = sorted(root.rglob("*.csv"))
    name = {spec.get("file_name")!r}
    if name:
        named = [path for path in found if path.name == name]
        if named:
            return named[0]
    return found[0] if found else None

def main():
    path = table()
    status = "missing_row"
    log = "missing table"
    detail = "The Kaggle input has no CSV."
    if path is not None:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        lines = []
        status = "match"
        detail = "The public table matches the count written in the paper."
        for check in SPEC["checks"]:
            op = check["op"]
            expected = check["expected"]
            if op == "rows":
                actual = len(rows)
                lines.append(f"rows {{actual}} expected {{expected}}")
                if int(actual) != int(expected):
                    status = "mismatch"
                    detail = f"The table has {{actual}} rows. The paper says {{expected}}."
                    break
                continue
            column = check["column"]
            if not rows or column not in rows[0]:
                status = "missing_row"
                detail = f"The table has no column {{column}}."
                lines.append(detail)
                break
            if op == "count_eq":
                actual = sum(1 for row in rows if str(row.get(column) or "").strip() == str(check["equals"]))
            elif op == "sum":
                actual = sum(float(row[column]) for row in rows if str(row.get(column) or "").strip())
            else:
                values = [float(row[column]) for row in rows if str(row.get(column) or "").strip()]
                actual = sum(values) / len(values) if values else 0
            lines.append(f"{{op}} {{column}} {{actual}} expected {{expected}}")
            if float(actual) != float(expected) and abs(float(actual) - float(expected)) > 1e-6:
                status = "mismatch"
                detail = f"The {{op}} of {{column}} is {{actual}}. The paper says {{expected}}."
                break
        log = "\\n".join(lines)
    payload = {{
        "where": "kaggle",
        "status": status,
        "log": log,
        "detail": detail,
        "claim_text": SPEC["claim_text"],
        "kernel_url": {KERNEL_URL!r},
    }}
    out = Path("/kaggle/working/results.json")
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(out.read_text(encoding="utf-8"))

if __name__ == "__main__":
    main()
"""


def push_kernel(spec: dict[str, Any]) -> dict[str, Any] | None:
    binary = _kaggle_bin()
    if not binary:
        return None
    if not os.environ.get("KAGGLE_USERNAME") or not os.environ.get("KAGGLE_KEY"):
        return None
    work = Path(tempfile.mkdtemp(prefix="arx-repro-"))
    try:
        (work / "repro_kernel.py").write_text(_kernel_source(spec), encoding="utf-8")
        metadata = {
            "id": KERNEL_ID,
            "title": "ArxAudit repro",
            "code_file": "repro_kernel.py",
            "language": "python",
            "kernel_type": "script",
            "is_private": "true",
            "enable_gpu": "false",
            "enable_internet": "false",
            "dataset_sources": [spec["dataset_slug"]],
            "competition_sources": [],
            "kernel_sources": [],
            "model_sources": [],
        }
        (work / "kernel-metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        pushed = subprocess.run(
            [binary, "kernels", "push", "-p", str(work)],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        log = ((pushed.stdout or "") + (pushed.stderr or ""))[-1500:]
        if pushed.returncode != 0:
            return {
                "where": "kaggle",
                "status": "not_run",
                "log": log,
                "kernel_url": KERNEL_URL,
                "detail": "The kernel push did not start.",
                "claim_text": spec.get("claim_text") or "",
            }
        deadline = time.time() + 120
        state = ""
        while time.time() < deadline:
            status = subprocess.run(
                [binary, "kernels", "status", KERNEL_ID],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            state = ((status.stdout or "") + (status.stderr or "")).upper()
            if "COMPLETE" in state or "ERROR" in state or "FAILED" in state:
                break
            time.sleep(8)
        out = work / "output"
        out.mkdir(exist_ok=True)
        subprocess.run(
            [binary, "kernels", "output", KERNEL_ID, "-p", str(out)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        results = out / "results.json"
        if not results.is_file():
            return {
                "where": "kaggle",
                "status": "not_run",
                "log": state[-1500:],
                "kernel_url": KERNEL_URL,
                "detail": "The kernel did not return a result yet.",
                "claim_text": spec.get("claim_text") or "",
            }
        payload = json.loads(results.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        payload["where"] = "kaggle"
        payload["kernel_url"] = KERNEL_URL
        return payload
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {
            "where": "kaggle",
            "status": "not_run",
            "log": "",
            "kernel_url": KERNEL_URL,
            "detail": "The kernel did not return a result yet.",
            "claim_text": spec.get("claim_text") or "",
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _dataset_sentences(claims: list[dict[str, Any]], sections: dict[str, str]) -> list[str]:
    import compiler

    seen: set[str] = set()
    sentences: list[str] = []

    def add(text: str) -> None:
        cleaned = " ".join(text.split()).strip()
        if len(cleaned) < 20 or cleaned in seen:
            return
        if not compiler.dataset_slug(cleaned) and not re.search(
            r"\b(rows|observations|passengers|samples|records)\b", cleaned, re.I
        ):
            return
        seen.add(cleaned)
        sentences.append(cleaned)

    for claim in claims:
        add(str(claim.get("text") or ""))
    for name in ("abstract", "methods", "results"):
        for part in re.split(r"(?<=[.!?])\s+", sections.get(name) or ""):
            add(part)
    return sentences


def _claim_id_for(sentence: str, claims: list[dict[str, Any]]) -> str:
    import hashlib

    for claim in claims:
        text = str(claim.get("text") or "")
        if text and (text in sentence or sentence in text) and claim.get("claim_id"):
            return str(claim["claim_id"])
    return hashlib.sha1(sentence.encode()).hexdigest()[:12]


def reproduce(
    claims: list[dict[str, Any]],
    sections: dict[str, str],
    *,
    model: Model | None = None,
    pusher: Pusher | None = None,
) -> list[dict[str, Any]]:
    """Compile each dataset sentence, resolve one table, and execute the DSL locally."""
    import compiler
    import datasets
    import dsl
    import pandas as pd
    from dsl import Spec, formula

    context = "\n".join(sections.get(name) or "" for name in ("methods", "results", "abstract"))
    mentioned = "\n".join(
        [context, *[str(claim.get("text") or "") for claim in claims]]
    )
    if not datasets.names_public_table(mentioned):
        return []
    computations: list[dict[str, Any]] = []
    acquired: dict[str, Any] = {}
    ask = model if model is not None else (lambda _text: None)
    for sentence in _dataset_sentences(claims, sections):
        specs = compiler.compile_claim(sentence, ask=ask)
        if not specs:
            continue
        resolved = datasets.resolve(f"{sentence}\n{context}", specs)
        steps = ["Located claim", *list(resolved.get("steps") or [])]
        slug = str(resolved.get("dataset_slug") or "")
        primary = next((spec for spec in specs if spec.operation.value != "ROWS"), specs[0])
        base: dict[str, Any] = {
            "claim_id": _claim_id_for(sentence, claims),
            "dataset_slug": slug,
            "resolution": resolved.get("resolution") or "not_found",
            "spec": primary.model_dump(mode="json"),
            "actual": None,
            "expected": primary.expected,
            "status": "could_not_run",
            "steps": steps,
            "log": "dataset not available on this machine",
            "formula": formula(primary),
        }
        if resolved.get("resolution") != "match" or not slug:
            if resolved.get("resolution") == "ambiguous":
                base["log"] = "Exact dataset version could not be verified."
            computations.append(base)
            continue
        if slug not in acquired:
            acquired[slug] = datasets.acquire_table(slug, "")
        table = acquired[slug]
        if table is None:
            computations.append(base)
            continue
        steps.append("Downloaded source data")
        try:
            frame = pd.read_csv(table)
        except (OSError, ValueError, pd.errors.ParserError):
            base["steps"] = steps
            base["log"] = "dataset not available on this machine"
            computations.append(base)
            continue
        outcomes = []
        for spec in specs:
            if not isinstance(spec, Spec):
                continue
            outcome = dsl.execute(spec, frame)
            outcomes.append(outcome)
            steps.append(f"Executed {spec.operation.value}")
            if outcome["status"] == "reproduced":
                steps.append(f"Reproduced: {outcome['actual']}")
            elif outcome["status"] == "could_not_reproduce":
                steps.append(f"Computed {outcome['actual']}, claimed {outcome['expected']}")
        chosen = next(
            (item for item in outcomes if item.get("status") == "could_not_reproduce"),
            next((item for item in outcomes if item.get("formula") == formula(primary)), outcomes[-1] if outcomes else None),
        )
        if chosen is None:
            computations.append(base)
            continue
        base.update(
            {
                "actual": chosen.get("actual"),
                "expected": chosen.get("expected"),
                "status": chosen.get("status") or "could_not_run",
                "formula": chosen.get("formula") or formula(primary),
                "log": chosen.get("log") or "",
                "steps": steps,
            }
        )
        if os.environ.get("ARX_KAGGLE_KERNEL") == "1":
            sender = pusher if pusher is not None else push_kernel
            try:
                sender({"dataset_slug": slug, "claim_text": sentence, "checks": [], "file_name": ""})
            except Exception:
                pass
        computations.append(base)
    return computations
