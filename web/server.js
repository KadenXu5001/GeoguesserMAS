const http = require("node:http");
const path = require("node:path");
const fs = require("node:fs/promises");
const { randomInt, randomUUID } = require("node:crypto");
const { spawn } = require("node:child_process");

const ROOT = path.resolve(__dirname, "..");
const PORT = Number(process.env.VISION_PORT || 3000);
const PYTHON = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const HEADINGS = [0, 90, 180, 270];
const REGION_NAMES = new Intl.DisplayNames(["en"], { type: "region" });

function send(res, status, body, type = "application/json", headers = {}) {
  res.writeHead(status, {
    "content-type": `${type}; charset=utf-8`,
    "cache-control": "no-store",
    ...headers,
  });
  res.end(type === "application/json" && !Buffer.isBuffer(body) ? JSON.stringify(body) : body);
}

async function readJson(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > 1024 * 1024) throw new Error("The request is larger than 1 MB.");
    chunks.push(chunk);
  }
  if (!chunks.length) return {};
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

function parseCsv(text) {
  const [header, ...lines] = text.trim().split(/\r?\n/);
  const columns = header.split(",");
  return lines.filter(Boolean).map((line) => {
    const values = line.split(",");
    return Object.fromEntries(columns.map((key, index) => [key, values[index]]));
  });
}

async function listTrainingPanoramas(root = ROOT) {
  const rows = [];
  for (const split of ["dev_v1", "eval_c1"]) {
    const text = await fs.readFile(path.join(root, "data", "datasets", `${split}.csv`), "utf8");
    for (const row of parseCsv(text)) {
      const width = Number(row.panorama_width);
      const height = Number(row.panorama_height);
      if (!row.panorama_path || width < height * 2) continue;
      const panoramaPath = path.resolve(root, row.panorama_path);
      try {
        await fs.access(panoramaPath);
      } catch {
        continue;
      }
      rows.push({
        sourceId: row.mapillary_image_id,
        countryIso2: row.country_iso2.toUpperCase(),
        country: row.country,
        panoramaPath,
        views: Object.fromEntries(HEADINGS.map((heading) => [
          heading,
          path.resolve(root, row[`view_h${String(heading).padStart(3, "0")}_path`]),
        ])),
      });
    }
  }
  return rows;
}

class RoundStore {
  constructor(panoramas, randomIndex = (length) => randomInt(length)) {
    this.panoramas = panoramas;
    this.randomIndex = randomIndex;
    this.rounds = new Map();
  }

  create(excludedRoundIds = []) {
    const excludedSources = new Set(
      excludedRoundIds.map((id) => this.rounds.get(id)?.panorama.sourceId).filter(Boolean),
    );
    let candidates = this.panoramas.filter((panorama) => !excludedSources.has(panorama.sourceId));
    if (!candidates.length) candidates = this.panoramas;
    if (!candidates.length) throw new Error("No playable panoramas are available.");
    const panorama = candidates[this.randomIndex(candidates.length)];
    const round = {
      id: randomUUID(),
      panorama,
      answered: false,
      result: null,
      createdAt: Date.now(),
    };
    this.rounds.set(round.id, round);
    return round;
  }

  get(roundId) {
    return this.rounds.get(roundId) || null;
  }

  guess(roundId, selectedIso2) {
    const round = this.get(roundId);
    if (!round) return { status: 404, body: { error: "Training round not found." } };
    if (round.answered) return { status: 409, body: { error: "This round has already been submitted." } };
    const normalized = String(selectedIso2 || "").trim().toUpperCase();
    if (!/^[A-Z]{2}$/.test(normalized)) {
      return { status: 400, body: { error: "Choose a valid country before guessing." } };
    }
    round.answered = true;
    round.result = {
      correct: normalized === round.panorama.countryIso2,
      selectedCountry: { iso2: normalized, name: REGION_NAMES.of(normalized) || normalized },
      correctCountry: {
        iso2: round.panorama.countryIso2,
        name: round.panorama.country || REGION_NAMES.of(round.panorama.countryIso2),
      },
    };
    return { status: 200, body: round.result };
  }
}

function serializeRound(round) {
  const payload = {
    roundId: round.id,
    panoramaUrl: `/api/rounds/${encodeURIComponent(round.id)}/panorama`,
    viewUrls: Object.fromEntries(HEADINGS.map((heading) => [
      heading,
      `/api/rounds/${encodeURIComponent(round.id)}/views/${heading}`,
    ])),
    answered: round.answered,
  };
  if (round.answered) payload.result = round.result;
  return payload;
}

async function runVisionAnalysis(paths, { root = ROOT, python = PYTHON } = {}) {
  const input = JSON.stringify({ paths, model: "gemini-3-flash-preview" });
  return new Promise((resolve, reject) => {
    const child = spawn(python, [path.join(root, "scripts", "run_vision_bbox.py")], {
      cwd: root,
      env: { ...process.env, PYTHONPATH: path.join(root, "src") },
      stdio: ["pipe", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) return reject(new Error(stderr || `Vision process exited with ${code}.`));
      try {
        resolve(JSON.parse(stdout));
      } catch {
        reject(new Error("Vision analysis returned malformed JSON."));
      }
    });
    child.stdin.end(input);
  });
}

function mediaType(target) {
  if (target.endsWith(".js")) return "text/javascript";
  if (target.endsWith(".css")) return "text/css";
  if (target.endsWith(".json") || target.endsWith(".geojson")) return "application/json";
  if (target.endsWith(".svg")) return "image/svg+xml";
  if (target.endsWith(".png")) return "image/png";
  if (target.endsWith(".jpg") || target.endsWith(".jpeg")) return "image/jpeg";
  return "text/html";
}

async function serveFrontend(res, requestPath, root = ROOT) {
  const distRoot = path.join(root, "web", "dist");
  const relative = requestPath === "/" ? "index.html" : requestPath.slice(1);
  const target = path.resolve(distRoot, relative);
  if (!target.startsWith(`${distRoot}${path.sep}`)) return false;
  try {
    const content = await fs.readFile(target);
    send(res, 200, content, mediaType(target));
    return true;
  } catch {
    if (requestPath !== "/") {
      try {
        const content = await fs.readFile(path.join(distRoot, "index.html"));
        send(res, 200, content, "text/html");
        return true;
      } catch {
        return false;
      }
    }
    return false;
  }
}

function createAppServer({
  root = ROOT,
  panoramas,
  analyze = (paths) => runVisionAnalysis(paths, { root }),
  randomIndex,
} = {}) {
  const panoramaPromise = panoramas ? Promise.resolve(panoramas) : listTrainingPanoramas(root);
  const storePromise = panoramaPromise.then((items) => new RoundStore(items, randomIndex));
  const analysisCache = new Map();

  return http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, "http://127.0.0.1");
      const store = await storePromise;

      if (req.method === "POST" && url.pathname === "/api/rounds") {
        const payload = await readJson(req);
        const excluded = Array.isArray(payload.excludeRoundIds) ? payload.excludeRoundIds : [];
        return send(res, 201, serializeRound(store.create(excluded)));
      }

      const roundMatch = url.pathname.match(/^\/api\/rounds\/([0-9a-f-]+)$/i);
      if (req.method === "GET" && roundMatch) {
        const round = store.get(roundMatch[1]);
        return round
          ? send(res, 200, serializeRound(round))
          : send(res, 404, { error: "Training round not found." });
      }

      const panoramaMatch = url.pathname.match(/^\/api\/rounds\/([0-9a-f-]+)\/panorama$/i);
      if (req.method === "GET" && panoramaMatch) {
        const round = store.get(panoramaMatch[1]);
        if (!round) return send(res, 404, { error: "Training round not found." });
        return send(res, 200, await fs.readFile(round.panorama.panoramaPath), "image/jpeg");
      }

      const viewMatch = url.pathname.match(/^\/api\/rounds\/([0-9a-f-]+)\/views\/(0|90|180|270)$/i);
      if (req.method === "GET" && viewMatch) {
        const round = store.get(viewMatch[1]);
        if (!round) return send(res, 404, { error: "Training round not found." });
        return send(res, 200, await fs.readFile(round.panorama.views[Number(viewMatch[2])]), "image/jpeg");
      }

      const guessMatch = url.pathname.match(/^\/api\/rounds\/([0-9a-f-]+)\/guess$/i);
      if (req.method === "POST" && guessMatch) {
        const payload = await readJson(req);
        const outcome = store.guess(guessMatch[1], payload.countryIso2);
        return send(res, outcome.status, outcome.body);
      }

      const analyzeMatch = url.pathname.match(/^\/api\/rounds\/([0-9a-f-]+)\/analyze$/i);
      if (req.method === "POST" && analyzeMatch) {
        const round = store.get(analyzeMatch[1]);
        if (!round) return send(res, 404, { error: "Training round not found." });
        const cacheKey = round.panorama.sourceId;
        const cached = analysisCache.has(cacheKey);
        if (!cached) {
          const task = analyze(HEADINGS.map((heading) => round.panorama.views[heading]));
          analysisCache.set(cacheKey, Promise.resolve(task));
        }
        try {
          const analysis = await analysisCache.get(cacheKey);
          return send(res, 200, { analysis, cached });
        } catch (error) {
          analysisCache.delete(cacheKey);
          throw error;
        }
      }

      if (req.method === "GET" && !url.pathname.startsWith("/api/") && await serveFrontend(res, url.pathname, root)) return;
      send(res, 404, { error: "Not found." });
    } catch (error) {
      send(res, 400, { error: error.message || "Request failed." });
    }
  });
}

if (require.main === module) {
  createAppServer().listen(PORT, "127.0.0.1", () => {
    console.log(`GeoGuessr training frontend: http://127.0.0.1:${PORT}`);
  });
}

module.exports = {
  RoundStore,
  createAppServer,
  listTrainingPanoramas,
  serializeRound,
};
