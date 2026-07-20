const http = require("node:http");
const path = require("node:path");
const fsSync = require("node:fs");
const fs = require("node:fs/promises");
const { createHash, randomInt, randomUUID } = require("node:crypto");
const { spawn } = require("node:child_process");
const { MongoClient } = require("mongodb");

const ROOT = path.resolve(__dirname, "..");
const PORT = Number(process.env.VISION_PORT || 3000);

function resolvePythonExecutable({
  root = ROOT,
  env = process.env,
  platform = process.platform,
  existsSync = fsSync.existsSync,
} = {}) {
  if (env.PYTHON) return env.PYTHON;
  const candidates = platform === "win32"
    ? [
      path.join(root, ".runtime-win", "Scripts", "python.exe"),
      path.join(root, ".venv", "Scripts", "python.exe"),
      path.join(root, "venv", "Scripts", "python.exe"),
    ]
    : [
      path.join(root, ".venv", "bin", "python"),
      path.join(root, ".runtime-venv", "bin", "python"),
    ];
  return candidates.find((candidate) => existsSync(candidate))
    || (platform === "win32" ? "python" : "python3");
}

const PYTHON = resolvePythonExecutable();
const HEADINGS = [0, 90, 180, 270];
const SOURCE_PRIVATE = "source-private";
const RUNTIME_PRIVATE = "runtime-private";
const REGION_NAMES = new Intl.DisplayNames(["en"], { type: "region" });
const VISION_ANALYSIS_CACHE_VERSION = process.env.VISION_ANALYSIS_CACHE_VERSION || "vision-analysis-v3";

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

async function listPilotTrainingPanoramas(root = ROOT) {
  const migrationOverlay = await loadStorageMigrationOverlay(root);
  const rows = [];
  for (const split of ["dev_v1", "eval_c1"]) {
    const text = await fs.readFile(path.join(root, "data", "datasets", `${split}.csv`), "utf8");
    for (const row of parseCsv(text)) {
      const width = Number(row.panorama_width);
      const height = Number(row.panorama_height);
      if (!row.panorama_path || width < height * 2) continue;
      const migrated = migrationOverlay.get(row.mapillary_image_id);
      const panoramaPath = path.resolve(
        root,
        migrated?.panorama_object_store_path || row.panorama_path,
      );
      try {
        await fs.access(panoramaPath);
      } catch {
        continue;
      }
      rows.push({
        sourceId: row.mapillary_image_id,
        datasetVersion: row.dataset_version,
        countryIso2: row.country_iso2.toUpperCase(),
        country: row.country,
        panoramaPath,
        views: Object.fromEntries(HEADINGS.map((heading) => [
          heading,
          path.resolve(
            root,
            migrated?.view_object_store_paths?.[heading]
              || row[`view_h${String(heading).padStart(3, "0")}_path`],
          ),
        ])),
        viewHashes: Object.fromEntries(HEADINGS.map((heading) => [
          heading,
          row[`view_h${String(heading).padStart(3, "0")}_sha256`],
        ])),
      });
    }
  }
  return rows;
}

function resolveObjectStoreMedia(root, reference, expectedNamespace, countryIso2, objectStoreRoot) {
  if (!reference || reference.storage_namespace !== expectedNamespace) return null;
  const objectKey = String(reference.object_key || "").replaceAll("\\", "/");
  const expectedPrefix = `countries/${countryIso2}/objects/`;
  if (!objectKey.startsWith(expectedPrefix)) return null;

  const storeRoot = path.resolve(
    objectStoreRoot || process.env.LOCAL_OBJECT_STORE_ROOT || path.join(root, ".local-data"),
  );
  const namespaceRoot = path.resolve(storeRoot, expectedNamespace);
  const target = path.resolve(namespaceRoot, ...objectKey.split("/"));
  if (!target.startsWith(`${namespaceRoot}${path.sep}`)) return null;
  return target;
}

async function listMongoTrainingPanoramas(root = ROOT, {
  database,
  mongoClient,
  uri = process.env.MONGODB_URI || "mongodb://localhost:27017",
  databaseName = process.env.MONGODB_DATABASE || "geoguesser",
  objectStoreRoot,
} = {}) {
  const definition = JSON.parse(await fs.readFile(
    path.join(root, "data", "dataset_definitions", "worldwide_v2.json"),
    "utf8",
  ));
  const playExclusions = new Set((definition.temporary_exclusions || [])
    .filter((item) => Array.isArray(item.scopes) && item.scopes.includes("play"))
    .map((item) => String(item.iso2).toUpperCase()));
  const countries = new Map(definition.countries
    .filter((item) => !playExclusions.has(String(item.iso2).toUpperCase()))
    .map((item) => [
    String(item.iso2).toUpperCase(),
    String(item.country),
    ]));

  let ownedClient;
  if (!database) {
    ownedClient = mongoClient || new MongoClient(uri, { serverSelectionTimeoutMS: 5000 });
    await ownedClient.connect();
    database = ownedClient.db(databaseName);
  }

  try {
    const records = await database.collection("panoramas").find({
      dataset_version: definition.version,
      country_iso2: { $in: [...countries.keys()] },
      status: { $in: ["quality_review", "rendered"] },
      "quality.automatic_pass": true,
    }, {
      projection: {
        _id: 0,
        mapillary_image_id: 1,
        country_iso2: 1,
        panorama_file: 1,
        rendered_views: 1,
      },
    }).toArray();

    const panoramas = [];
    for (const record of records) {
      const countryIso2 = String(record.country_iso2 || "").toUpperCase();
      const panoramaFile = record.panorama_file || {};
      const width = Number(panoramaFile.width);
      const height = Number(panoramaFile.height);
      if (!countries.has(countryIso2) || width <= 0 || height <= 0 || width !== height * 2) continue;

      const panoramaPath = resolveObjectStoreMedia(
        root, panoramaFile, SOURCE_PRIVATE, countryIso2, objectStoreRoot,
      );
      const viewEntries = Array.isArray(record.rendered_views) ? record.rendered_views : [];
      const byHeading = new Map(viewEntries.map((view) => [Number(view.heading), view]));
      if (byHeading.size !== HEADINGS.length || HEADINGS.some((heading) => !byHeading.has(heading))) continue;

      const views = {};
      const viewHashes = {};
      let eligible = Boolean(panoramaPath);
      for (const heading of HEADINGS) {
        const view = byHeading.get(heading);
        const target = resolveObjectStoreMedia(
          root, view, RUNTIME_PRIVATE, countryIso2, objectStoreRoot,
        );
        if (!target || !/^[0-9a-f]{64}$/i.test(String(view.sha256 || ""))) eligible = false;
        views[heading] = target;
        viewHashes[heading] = view.sha256;
      }
      if (!eligible) continue;

      try {
        await Promise.all([panoramaPath, ...Object.values(views)].map((target) => fs.access(target)));
      } catch {
        continue;
      }

      panoramas.push({
        sourceId: String(record.mapillary_image_id),
        datasetVersion: definition.version,
        countryIso2,
        country: countries.get(countryIso2),
        panoramaPath,
        views,
        viewHashes,
      });
    }
    return panoramas;
  } finally {
    await ownedClient?.close();
  }
}

function mergeTrainingPanoramas(pilot, worldwide) {
  const seen = new Set(pilot.map((panorama) => panorama.sourceId));
  return [...pilot, ...worldwide.filter((panorama) => {
    if (seen.has(panorama.sourceId)) return false;
    seen.add(panorama.sourceId);
    return true;
  })];
}

async function listTrainingPanoramas(root = ROOT, options = {}) {
  const [pilot, worldwide] = await Promise.all([
    listPilotTrainingPanoramas(root),
    listMongoTrainingPanoramas(root, options),
  ]);
  return mergeTrainingPanoramas(pilot, worldwide);
}

async function loadStorageMigrationOverlay(root = ROOT) {
  const reportPath = path.join(root, "data", "migrations", "pilot_v1_object_store.json");
  try {
    const report = JSON.parse(await fs.readFile(reportPath, "utf8"));
    if (report.status !== "complete" || report.dataset_version !== "pilot_v1") return new Map();
    return new Map((report.items || []).map((item) => [item.provider_image_id, item]));
  } catch (error) {
    if (error.code === "ENOENT") return new Map();
    throw error;
  }
}

function visionAnalysisCacheKey(panorama) {
  const identity = {
    version: VISION_ANALYSIS_CACHE_VERSION,
    sourceId: panorama.sourceId,
    viewHashes: HEADINGS.map((heading) => panorama.viewHashes?.[heading] || null),
  };
  return createHash("sha256").update(JSON.stringify(identity)).digest("hex");
}

function browserSafeAnalysisPayload(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Vision analysis did not return an object.");
  }
  if (!value.analysis || typeof value.analysis !== "object" || Array.isArray(value.analysis)) {
    throw new Error("Vision analysis did not return structured extraction data.");
  }
  if (!Array.isArray(value.informedEvidence)) {
    throw new Error("Vision analysis did not return an informed-evidence list.");
  }
  if (typeof value.predictedCountry !== "string" || !value.predictedCountry.trim()) {
    throw new Error("Vision analysis did not return the agent's predicted country.");
  }
  if (!Array.isArray(value.alternativeCountries)) {
    throw new Error("Vision analysis did not return the agent's alternative countries.");
  }
  const predictedCountry = value.predictedCountry.trim();
  const alternativeCountries = [...new Set(value.alternativeCountries
    .filter((country) => typeof country === "string")
    .map((country) => country.trim())
    .filter((country) => country && country !== predictedCountry))].slice(0, 3);
  return {
    analysis: value.analysis,
    informedEvidence: value.informedEvidence,
    predictedCountry,
    alternativeCountries,
  };
}

function createMongoAnalysisStore({
  uri = process.env.MONGODB_URI || "mongodb://localhost:27017",
  databaseName = process.env.MONGODB_DATABASE || "geoguesser",
} = {}) {
  const client = new MongoClient(uri, { serverSelectionTimeoutMS: 5000 });
  let collectionPromise;

  function collection() {
    if (!collectionPromise) {
      collectionPromise = client.connect().then(() => client
        .db(databaseName)
        .collection("vision_analysis_cache"));
    }
    return collectionPromise;
  }

  return {
    async get(cacheKey) {
      const document = await (await collection()).findOne({ _id: cacheKey });
      return document ? browserSafeAnalysisPayload(document.payload) : null;
    },
    async set(cacheKey, payload, metadata) {
      const safePayload = browserSafeAnalysisPayload(payload);
      await (await collection()).updateOne(
        { _id: cacheKey },
        {
          $set: {
            cache_version: VISION_ANALYSIS_CACHE_VERSION,
            source_id: metadata.sourceId,
            view_hashes: metadata.viewHashes,
            payload: safePayload,
            updated_at: new Date(),
          },
          $setOnInsert: { created_at: new Date() },
        },
        { upsert: true },
      );
    },
    async close() {
      await client.close();
    },
  };
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

async function runVisionAnalysis(
  request,
  { root = ROOT, python = PYTHON, spawnProcess = spawn } = {},
) {
  const input = JSON.stringify(Array.isArray(request) ? { paths: request } : request);
  return new Promise((resolve, reject) => {
    const child = spawnProcess(python, [path.join(root, "scripts", "run_vision_mas.py")], {
      cwd: root,
      env: {
        ...process.env,
        PYTHONPATH: path.join(root, "src"),
        PYTHONIOENCODING: "utf-8",
        PYTHONUTF8: "1",
      },
      stdio: ["pipe", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    let settled = false;
    const resolveCompletedPrediction = () => {
      if (settled) return true;
      try {
        const result = JSON.parse(stdout);
        settled = true;
        resolve(result);
        return true;
      } catch {
        return false;
      }
    };
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
      resolveCompletedPrediction();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
      process.stderr.write(chunk);
    });
    child.on("error", (error) => {
      if (!settled) reject(error);
    });
    child.on("close", (code) => {
      if (code !== 0) {
        if (!stderr) console.error(`Vision process exited with ${code}.`);
        if (!settled) reject(new Error(stderr || `Vision process exited with ${code}.`));
        return;
      }
      if (!resolveCompletedPrediction()) {
        settled = true;
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

function visionMasRequest(panorama) {
  return {
    imageId: panorama.sourceId,
    datasetVersion: panorama.datasetVersion,
    paths: HEADINGS.map((heading) => panorama.views[heading]),
    viewHashes: HEADINGS.map((heading) => panorama.viewHashes[heading]),
  };
}

function isRetryableVisionError(error) {
  const detail = `${error?.name || ""} ${error?.code || ""} ${error?.message || error || ""}`
    .toLowerCase();
  // Trace delivery happens after inference. Retrying would rerun a completed MAS
  // prediction and can multiply the same oversized or unavailable upload.
  if (detail.includes("langsmith_observability_failure")) return false;
  const status = Number(error?.status || error?.statusCode || error?.code);
  if ([429, 500, 503, 504].includes(status)) return true;
  return [
    "readtimeout",
    "writetimeout",
    "connecttimeout",
    "pooltimeout",
    "connecterror",
    "remoteprotocolerror",
    "timeout error",
    "timed out",
    "deadline exceeded",
    "resource_exhausted",
    "too many requests",
    "service unavailable",
    "503 unavailable",
    "internal server error",
  ].some((marker) => detail.includes(marker));
}

async function analyzeWithTransientRetry(analyze, request) {
  try {
    return await analyze(request);
  } catch (error) {
    if (!isRetryableVisionError(error)) throw error;
    console.warn("Vision MAS transient failure; starting one fresh website retry.");
    return analyze(request);
  }
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
  analyze = (request) => runVisionAnalysis(request, { root }),
  analysisStore = createMongoAnalysisStore(),
  randomIndex,
} = {}) {
  const panoramaPromise = panoramas ? Promise.resolve(panoramas) : listTrainingPanoramas(root);
  const storePromise = panoramaPromise.then((items) => new RoundStore(items, randomIndex));
  const inFlightAnalyses = new Map();

  const server = http.createServer(async (req, res) => {
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
        const cacheKey = visionAnalysisCacheKey(round.panorama);
        const persisted = await analysisStore.get(cacheKey);
        if (persisted) {
          return send(res, 200, { ...persisted, cached: true });
        }

        let task = inFlightAnalyses.get(cacheKey);
        if (!task) {
          task = (async () => {
            const generated = browserSafeAnalysisPayload(
              await analyzeWithTransientRetry(analyze, visionMasRequest(round.panorama)),
            );
            await analysisStore.set(cacheKey, generated, {
              sourceId: round.panorama.sourceId,
              viewHashes: HEADINGS.map((heading) => round.panorama.viewHashes?.[heading] || null),
            });
            return generated;
          })();
          inFlightAnalyses.set(cacheKey, task);
        }
        try {
          const analysis = await task;
          return send(res, 200, { ...analysis, cached: false });
        } catch (error) {
          throw error;
        } finally {
          if (inFlightAnalyses.get(cacheKey) === task) inFlightAnalyses.delete(cacheKey);
        }
      }

      if (req.method === "GET" && !url.pathname.startsWith("/api/") && await serveFrontend(res, url.pathname, root)) return;
      send(res, 404, { error: "Not found." });
    } catch (error) {
      send(res, 400, { error: error.message || "Request failed." });
    }
  });
  server.on("close", () => { void analysisStore.close?.(); });
  return server;
}

if (require.main === module) {
  createAppServer().listen(PORT, "127.0.0.1", () => {
    console.log(`GeoGuessr training frontend: http://127.0.0.1:${PORT}`);
    console.log(`Vision MAS Python: ${PYTHON}`);
  });
}

module.exports = {
  RoundStore,
  analyzeWithTransientRetry,
  browserSafeAnalysisPayload,
  createAppServer,
  createMongoAnalysisStore,
  listMongoTrainingPanoramas,
  listPilotTrainingPanoramas,
  listTrainingPanoramas,
  loadStorageMigrationOverlay,
  mergeTrainingPanoramas,
  isRetryableVisionError,
  resolvePythonExecutable,
  runVisionAnalysis,
  serializeRound,
  visionMasRequest,
  visionAnalysisCacheKey,
};
