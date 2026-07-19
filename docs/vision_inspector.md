# Local Vision MAS Guide

The guide selects a panorama from the same `data/datasets/dev_v1.csv` or `eval_c1.csv` manifests
used by MAS. Its first visit runs the production MAS once for the panorama and persists the
browser-safe result in MongoDB. Later visits, including visits after a website restart, read that
website cache without starting the MAS process.
The browser receives the structured extraction plus up to three highlightable evidence items; it
does not receive the final predicted country or alternatives.

`What the agent sees` displays every extracted bounding box. `What the agent informs` displays one
final-prediction evidence item at a time, associated with the exact extracted object cited by the
successful specialist lookup. Hovering or focusing that highlight shows the final evidence text.

From the inspector directory:

```powershell
cd web
npm install
npm start
```

Then open <http://localhost:3000>. `GEMINI_API_KEY` and `LANGSMITH_API_KEY` must be present in the
repository `.env` or process environment. Trace delivery is synchronous, and the guide reports a
failed MAS or trace upload as a recoverable analysis error.

MongoDB must also be running (`docker compose up -d mongodb`). The website uses `MONGODB_URI` and
`MONGODB_DATABASE` when provided, otherwise `mongodb://localhost:27017` and `geoguesser`. Run
`python main.py init-mongodb` after schema changes. Set `VISION_ANALYSIS_CACHE_VERSION` to a new
value when a changed analysis contract should force every panorama to be analyzed again.
