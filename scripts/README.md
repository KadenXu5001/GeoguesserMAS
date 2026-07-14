# Baseline scripts

From the repository root, activate the project virtual environment and run:

```powershell
& .\.venv\Scripts\Activate.ps1
python scripts\run_gemini_pro.py --limit 1
```

Run the complete development manifest with:

```powershell
python scripts\run_gemini_pro.py --dataset data\datasets\dev_v1.csv --limit 0
```

The script uses Google's current `gemini-3.1-pro-preview` model. Each panorama is written as one JSONL record under `.artifacts/`. MAS LangSmith
tracing is enabled for debugging. Uploads are synchronous because the trace
contains four multimodal inputs and must finish before the process exits.
`gemini-pro-baseline` run in the configured project.
