# Local Gemini Vision Inspector

The inspector selects a panorama from the same `data/datasets/dev_v1.csv` or `eval_c1.csv`
manifests used by MAS. It sends that row's exact four rendered cardinal views to
`gemini-3-flash-preview` through the existing Python extractor and displays returned boxes on the
selected direction.

From the inspector directory:

```powershell
cd web
npm install
npm start
```

Then open <http://localhost:3000>. `GEMINI_API_KEY` must be present in the repository `.env` or the process environment.
