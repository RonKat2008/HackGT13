# AGENTS.md

HackGT 13. The plans are the build order. Go one step at a time. Use subagents. Verify before the next step.

## Which plan

1. Finish [docs/plan-orchestrator.md](docs/plan-orchestrator.md) until its "Done when" section is true.
2. Then build the product the user names:
   - [docs/plan-stormcite.md](docs/plan-stormcite.md) — any research paper. Hallucinated results. AI-written vs human-written scores from Kaggle representations. AI-likeness is not proof.
   - [docs/plan-landfall.md](docs/plan-landfall.md) — one storm, one metro, public data only.
3. If the user has not picked a product, stop after the orchestrator and ask. Do not build both.

StormCite is not a hurricane-paper tool. Do not narrow it back to storms.

## Subagents

The parent coordinates. A subagent does one step and cannot see this chat. Every prompt must include the step id, the file list, the do-list, and the verify commands.

For the first step in the active plan whose verify command is not already passing:

1. Spawn one implementation subagent with the Task tool. Use `tdd-guide` for code steps and `generalPurpose` for notebooks, Kaggle pushes, and UI steps.
2. Tell it not to start the next step and not to edit files outside the list.
3. Wait.
4. Run the verify commands yourself. Read the output.
5. On failure, spawn one fix subagent with that output. Same step. Do not continue.
6. On success, spawn one `code-reviewer`. Python steps also get `python-reviewer`. TSX steps also get `react-reviewer`. One reviewer at a time. Fix only what breaks the step's pass bar.
7. Then, and only then, open the next step.

Do not run a swarm. Do not hand a subagent a whole plan. Two steps run at once only when both say they are parallel-ok and their file lists do not overlap. Person A and Person B tracks may run together only after the plan says the dependency is met (orchestrator O2 before web W1, StormCite S15 before UI U1, Landfall L9 before map M1).

## Pass bar

- Verify commands exited 0, or the step's manual check is written in the subagent's return.
- New behavior has a test, unless the step is a UI check that names what the parent must look at.
- No secrets in git. `.env` stays untracked.
- The subagent did not edit the next step's files.

## Rules on every step

- Recursive improvement is the playbook in [docs/plan-orchestrator.md](docs/plan-orchestrator.md): typed patches (`query_template`, `prompt_rule`, `span_window`), fitness after each run, live vs archived, and `POST /runs/{id}/replay`. Agents do not edit their own source to make a run pass. A patch that makes fitness fall is archived. A patch that drops facts from a claim is blocked by the retry-guard Jev check.
- Jev (OpenRouter Decisions API) judges a claim against evidence text. Grok writes prose. Parsers, pytest, and citation lookups run before Jev.
- On StormCite, a high AI-likeness score never creates an issue by itself. Issues come from failed citations, failed number checks, low claim-to-evidence similarity, or a failed Kaggle rerun. If the probe AUC on the Kaggle holdout is under 0.60, hide AI-likeness.
- Keys: `XAI_API_KEY`, `OPENROUTER_API_KEY`, `KAGGLE_USERNAME`, `KAGGLE_KEY`. Never `NEXT_PUBLIC_`.
- Voice is StormCite's briefing and Landfall's sitrep. Imagine is Landfall only, labeled generated footage.
- Public data only. No private cameras, no 911 or CAD calls, no posting verdicts to X.
- Do not commit unless the user asks.

## Subagent prompt

```
You are implementing ONE step of the HackGT build.

Plan file: <path>
Step id: <id>
Goal: <one sentence>

Files you may edit:
- ...

Do not edit anything else. Do not start the next step.

Do:
1. ...

Verify (must exit 0):
- ...

Return: files changed, verify output, anything still failing.
```

## If you are a subagent

You have one step. Finish it. Run its verify command. Stop. If you need a file outside your list, stop and say which file.
