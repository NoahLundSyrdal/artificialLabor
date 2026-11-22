# artificialLabor

Can an LLM agent earn money on freelance marketplaces? This repo takes real freelance ads,
decides which ones an agent can deliver profitably, writes the bid, does the work, and has a
second model QA the delivery.

Started at the Artificial Labor Hackathon (14 Dec 2025); rewritten since.

```
ad.md ──► parse ──► assess ──► economics ──► propose ──► execute ──► verify ──► report
          (LLM)     (LLM)      (code)        (LLM)       (LLM+code)  (LLM)
```

| Stage | What it does |
|---|---|
| parse | Extracts title, budget, currency, fixed/hourly, deliverables, what the client provides. |
| assess | Scores 5 feasibility factors, lists blockers, estimates human hours and LLM tokens. |
| economics | Converts the budget to USD, computes revenue, LLM cost, margin and a bid. Pure code. |
| decide | Go only if the job is open, feasibility ≥ 0.6, no blockers and margin ≥ 30%. |
| propose | Writes a short client proposal with the computed bid. |
| execute | The code model writes one Python script that reads `inputs/` and writes `outputs/`. It runs in a separate process with a timeout and no API keys in its environment. Errors are fed back for up to 3 attempts. |
| verify | A QA pass sees the inputs, the script and previews of every output (images included) and checks each deliverable and acceptance criterion. |

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # add MISTRAL_API_KEY (or OPENAI_API_KEY / OPENROUTER_API_KEY)

artificial-labor list                      # show the ads
artificial-labor run --only 01 07          # a couple of jobs
artificial-labor run                       # everything, results in runs/<timestamp>/
```

Useful flags: `--no-execute` (stop after proposals), `--force` (run no-go jobs anyway),
`--workers N`, `--max-attempts N`, `--timeout SECONDS`, `--min-score`, `--min-margin`.

Any OpenAI-compatible API works. Presets exist for `mistral` (default: `mistral-medium-latest`
for analysis, `codestral-latest` for code), `openai` and `openrouter`; or set `LLM_BASE_URL`,
`LLM_API_KEY`, `LLM_MODEL` and `LLM_CODE_MODEL`. See [.env.example](.env.example).

## Adding jobs

Each job is a folder in `data/ads/`:

```
data/ads/07-excel-csv-prefix-sort-dedupe/
├── ad.md          # the ad text, pasted as-is from the marketplace
├── brief.json     # optional: extra details/acceptance criteria the client sent later
└── inputs/        # optional: files the client provided
```

The ads in this repo are real postings collected in Dec 2025.
The `inputs/` and `brief.json` files are synthetic stand-ins for what the client would send.
Jobs that need client files the folder doesn't have get a proposal but are not executed.

## Output

```
runs/<timestamp>/
├── report.md                  # summary table + per-job details
├── results.json               # everything, machine-readable
└── jobs/<id>/
    ├── record.json            # parsed job, assessment, economics, decision, QA, LLM usage
    ├── proposal.md
    └── workspace/             # inputs/, solution.py, outputs/ (the deliverables)
```

## Safety

Executing model-written code is the point of this project. The runner strips secrets from the
environment and confines the working directory, but it is **not** a security sandbox: the
script runs with your user's permissions. Run it in a container or VM if you feed it ads
you don't trust.

## Development

```bash
pre-commit install
pytest           # uses a fake LLM, no API key or network needed
ruff check . && ruff format .
```

Code lives in `src/artificial_labor/`: `stages.py` (LLM prompts and stages), `economics.py`,
`sandbox.py`, `pipeline.py`, `report.py`, `cli.py`.
