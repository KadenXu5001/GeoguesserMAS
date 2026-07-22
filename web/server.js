const http = require("node:http");
const path = require("node:path");
const fsSync = require("node:fs");
const fs = require("node:fs/promises");
const { createHash, randomInt, randomUUID } = require("node:crypto");
const { spawn } = require("node:child_process");
const { MongoClient } = require("mongodb");

const ROOT = path.resolve(__dirname, "..");
const PORT = Number(process.env.PORT || process.env.VISION_PORT || 3000);
const HOST = process.env.HOST || "0.0.0.0";

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
const VISION_ANALYSIS_DEADLINE_MS = positiveMilliseconds(
  process.env.VISION_ANALYSIS_DEADLINE_MS,
  215_000,
);
const VISION_ANALYSIS_TERMINATION_GRACE_MS = positiveMilliseconds(
  process.env.VISION_ANALYSIS_TERMINATION_GRACE_MS,
  15_000,
);

class HttpError extends Error {
  constructor(status, message, headers = {}) {
    super(message);
    this.status = status;
    this.headers = headers;
  }
}

function enabled(value) {
  return /^(1|true|yes)$/i.test(String(value || ""));
}

function boundedNumber(value, fallback, minimum = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= minimum ? parsed : fallback;
}

function requestIdentity(req, {
  required = enabled(process.env.REQUIRE_PROXY_AUTH),
  trustProxy = enabled(process.env.TRUST_PROXY_HEADERS),
  userHeader = process.env.AUTH_USER_HEADER || "x-authenticated-user",
} = {}) {
  const forwardedUser = trustProxy ? String(req.headers[userHeader] || "").trim() : "";
  if (forwardedUser && !/^[\w.@+-]{1,128}$/.test(forwardedUser)) {
    throw new HttpError(400, "Invalid authenticated user header.");
  }
  if (required && !forwardedUser) throw new HttpError(401, "Authentication is required.");
  const address = trustProxy
    ? String(req.headers["x-real-ip"] || "").trim()
    : String(req.socket?.remoteAddress || "unknown");
  return { userId: forwardedUser || "anonymous", ip: address.slice(0, 128) || "unknown" };
}

function positiveMilliseconds(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

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

function createMongoRoundStore(panoramas, {
  uri = process.env.MONGODB_URI || "mongodb://localhost:27017",
  databaseName = process.env.MONGODB_DATABASE || "geoguesser",
  ttlHours = boundedNumber(process.env.ACTIVE_ROUND_TTL_HOURS, 24, 1),
  randomIndex = (length) => randomInt(length),
  client = new MongoClient(uri),
} = {}) {
  const collection = client.db(databaseName).collection("active_rounds");
  const toRound = (document) => document && ({
    id: document._id,
    panorama: document.panorama,
    answered: document.answered,
    result: document.result || null,
    createdAt: document.created_at?.getTime?.() || Date.now(),
  });
  return {
    async create(excludedRoundIds = [], ownerId = "anonymous") {
      const prior = excludedRoundIds.length
        ? await collection.find({ _id: { $in: excludedRoundIds }, owner_id: ownerId })
          .project({ "panorama.sourceId": 1 }).toArray()
        : [];
      const excludedSources = new Set(prior.map((item) => item.panorama?.sourceId).filter(Boolean));
      let candidates = panoramas.filter((item) => !excludedSources.has(item.sourceId));
      if (!candidates.length) candidates = panoramas;
      if (!candidates.length) throw new HttpError(503, "No playable panoramas are available.");
      const now = new Date();
      const document = {
        _id: randomUUID(), owner_id: ownerId,
        panorama: candidates[randomIndex(candidates.length)],
        answered: false, result: null, created_at: now,
        expires_at: new Date(now.getTime() + ttlHours * 60 * 60 * 1000),
      };
      await collection.insertOne(document);
      return toRound(document);
    },
    async get(roundId, ownerId = "anonymous") {
      return toRound(await collection.findOne({ _id: roundId, owner_id: ownerId }));
    },
    async guess(roundId, selectedIso2, ownerId = "anonymous") {
      const normalized = String(selectedIso2 || "").trim().toUpperCase();
      if (!/^[A-Z]{2}$/.test(normalized)) {
        return { status: 400, body: { error: "Choose a valid country before guessing." } };
      }
      const existing = await collection.findOne({ _id: roundId, owner_id: ownerId });
      if (!existing) return { status: 404, body: { error: "Training round not found." } };
      if (existing.answered) {
        return { status: 409, body: { error: "This round has already been submitted." } };
      }
      const result = {
        correct: normalized === existing.panorama.countryIso2,
        selectedCountry: { iso2: normalized, name: REGION_NAMES.of(normalized) || normalized },
        correctCountry: {
          iso2: existing.panorama.countryIso2,
          name: existing.panorama.country || REGION_NAMES.of(existing.panorama.countryIso2),
        },
      };
      const updated = await collection.findOneAndUpdate(
        { _id: roundId, owner_id: ownerId, answered: false },
        { $set: { answered: true, result } },
        { returnDocument: "after" },
      );
      if (!updated) {
        return { status: 409, body: { error: "This round has already been submitted." } };
      }
      return { status: 200, body: result };
    },
    async close() { await client.close(); },
  };
}

function createMongoRequestGuard({
  uri = process.env.MONGODB_URI || "mongodb://localhost:27017",
  databaseName = process.env.MONGODB_DATABASE || "geoguesser",
  userLimit = boundedNumber(process.env.MAS_USER_REQUESTS_PER_HOUR, 6, 1),
  ipLimit = boundedNumber(process.env.MAS_IP_REQUESTS_PER_HOUR, 12, 1),
  windowSeconds = boundedNumber(process.env.MAS_RATE_WINDOW_SECONDS, 3600, 1),
  client = new MongoClient(uri),
} = {}) {
  const collection = client.db(databaseName).collection("request_limits");
  const digest = (value) => createHash("sha256").update(value).digest("hex");
  async function increment(kind, value, limit, now = Date.now()) {
    const windowStart = Math.floor(now / (windowSeconds * 1000)) * windowSeconds;
    const id = `${kind}:${digest(value)}:${windowStart}`;
    const result = await collection.findOneAndUpdate(
      { _id: id },
      {
        $inc: { count: 1 },
        $setOnInsert: { expires_at: new Date((windowStart + windowSeconds * 2) * 1000) },
      },
      { upsert: true, returnDocument: "after" },
    );
    if (result.count > limit) {
      const retryAfter = Math.max(1, windowStart + windowSeconds - Math.floor(now / 1000));
      throw new HttpError(429, "Vision analysis rate limit exceeded.", {
        "retry-after": String(retryAfter),
      });
    }
  }
  return {
    async check({ userId, ip }) {
      await increment("user", userId, userLimit);
      await increment("ip", ip, ipLimit);
    },
    async close() { await client.close(); },
  };
}

function createMongoMasBudget({
  uri = process.env.MONGODB_URI || "mongodb://localhost:27017",
  databaseName = process.env.MONGODB_DATABASE || "geoguesser",
  monthlyLimitUsd = boundedNumber(process.env.MONTHLY_MAS_BUDGET_USD, 3, 0.01),
  reserveUsd = boundedNumber(process.env.MAS_MAX_REQUEST_RESERVATION_USD, 1, 0.01),
  client = new MongoClient(uri),
} = {}) {
  const collection = client.db(databaseName).collection("runtime_budgets");
  return {
    async reserve(now = new Date()) {
      const period = now.toISOString().slice(0, 7);
      const expiresAt = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 2, 1));
      try {
        await collection.updateOne(
          { _id: period },
          { $setOnInsert: { spent_usd: 0, reserved_usd: 0, expires_at: expiresAt } },
          { upsert: true },
        );
        const document = await collection.findOneAndUpdate(
          {
            _id: period,
            $expr: { $lte: [
              { $add: [
                { $ifNull: ["$spent_usd", 0] },
                { $ifNull: ["$reserved_usd", 0] },
                reserveUsd,
              ] },
              monthlyLimitUsd,
            ] },
          },
          {
            $inc: { reserved_usd: reserveUsd },
          },
          { returnDocument: "after" },
        );
        if (!document) throw new Error("budget unavailable");
      } catch (error) {
        if (error?.code === 11000 || /budget unavailable/i.test(error.message || "")) {
          throw new HttpError(503, "The monthly Vision analysis budget has been reached.");
        }
        throw error;
      }
      return { period, reserveUsd };
    },
    async settle(reservation, chargedUsd) {
      const charge = Math.max(0, Math.min(reservation.reserveUsd, Number(chargedUsd) || 0));
      await collection.updateOne(
        { _id: reservation.period },
        { $inc: { reserved_usd: -reservation.reserveUsd, spent_usd: charge } },
      );
    },
    async close() { await client.close(); },
  };
}

class Semaphore {
  constructor(limit = 1, maxQueue = Number.POSITIVE_INFINITY) {
    this.limit = limit; this.maxQueue = maxQueue; this.active = 0; this.waiters = [];
  }
  async use(task) {
    if (this.active >= this.limit) {
      if (this.waiters.length >= this.maxQueue) {
        throw new HttpError(503, "Vision analysis is busy; try again shortly.", {
          "retry-after": "5",
        });
      }
      await new Promise((resolve) => this.waiters.push(resolve));
    }
    this.active += 1;
    try { return await task(); } finally {
      this.active -= 1;
      this.waiters.shift()?.();
    }
  }
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
  {
    root = ROOT,
    python = PYTHON,
    spawnProcess = spawn,
    deadlineMs = VISION_ANALYSIS_DEADLINE_MS,
    terminationGraceMs = VISION_ANALYSIS_TERMINATION_GRACE_MS,
    activeChildren,
  } = {},
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
    activeChildren?.add(child);
    let stdout = "";
    let stderr = "";
    let settled = false;
    let processClosed = false;
    let outerDeadlineReached = false;
    let forceTerminationTimer;
    const deadlineError = () => {
      const error = new Error(
        `Vision MAS child exceeded its ${deadlineMs} ms outer process deadline.`,
      );
      error.code = "VISION_ANALYSIS_OUTER_DEADLINE";
      return error;
    };
    const deadlineTimer = setTimeout(() => {
      if (processClosed) return;
      outerDeadlineReached = true;
      console.error(
        `Vision MAS child reached its ${deadlineMs} ms outer deadline; requesting termination.`,
      );
      try {
        child.kill("SIGTERM");
      } catch (error) {
        console.error(`Vision MAS graceful termination request failed: ${error.message || error}`);
      }
      forceTerminationTimer = setTimeout(() => {
        if (processClosed) return;
        console.error(
          "LANGSMITH_OBSERVABILITY_FAILURE: Vision MAS child did not exit during its "
            + `${terminationGraceMs} ms trace-cleanup grace; forcing termination.`,
        );
        try {
          child.kill("SIGKILL");
        } catch (error) {
          console.error(`Vision MAS forced termination failed: ${error.message || error}`);
        }
      }, terminationGraceMs);
    }, deadlineMs);
    const resolveCompletedPrediction = () => {
      if (settled || outerDeadlineReached) return settled;
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
      if (!settled && !outerDeadlineReached) {
        settled = true;
        reject(error);
      }
    });
    child.on("close", (code) => {
      activeChildren?.delete(child);
      processClosed = true;
      clearTimeout(deadlineTimer);
      clearTimeout(forceTerminationTimer);
      if (outerDeadlineReached) {
        if (!settled) {
          settled = true;
          reject(deadlineError());
        }
        return;
      }
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

function isWholeRunTimeout(error) {
  const detail = `${error?.name || ""} ${error?.code || ""} ${error?.message || error || ""}`
    .toLowerCase();
  // Only a timeout before a structured result permits one new, isolated MAS run.
  // Capacity, provider, validation, and observability failures remain terminal.
  if (detail.includes("vision_analysis_outer_deadline")) return false;
  if (detail.includes("langsmith_observability_failure")) return false;
  const status = Number(error?.status || error?.statusCode || error?.code);
  if (status === 504) return true;
  return [
    "etimedout",
    "readtimeout",
    "writetimeout",
    "connecttimeout",
    "pooltimeout",
    "timeout error",
    "timed out",
    "deadline exceeded",
  ].some((marker) => detail.includes(marker));
}

async function analyzeWithTimeoutRetry(analyze, request, onRetry = async () => {}) {
  try {
    return await analyze(request);
  } catch (error) {
    if (!isWholeRunTimeout(error)) throw error;
    await onRetry(error);
    console.warn("Vision MAS timed out; starting one fresh, isolated MAS run.");
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
  analyze,
  analysisStore = createMongoAnalysisStore(),
  roundStore,
  requestGuard,
  masBudget,
  semaphore = new Semaphore(
    boundedNumber(process.env.MAS_CONCURRENCY_LIMIT, 1, 1),
    boundedNumber(process.env.MAS_MAX_QUEUE, 0),
  ),
  authOptions,
  randomIndex,
} = {}) {
  const activeChildren = new Set();
  const analyzeFn = analyze || ((request) => runVisionAnalysis(request, { root, activeChildren }));
  const panoramaPromise = panoramas ? Promise.resolve(panoramas) : listTrainingPanoramas(root);
  const storePromise = panoramaPromise.then((items) => roundStore || (
    enabled(process.env.PERSIST_ROUNDS_IN_MONGODB)
      ? createMongoRoundStore(items, { randomIndex })
      : new RoundStore(items, randomIndex)
  ));
  storePromise.catch(() => {});
  const inFlightAnalyses = new Map();
  const guard = requestGuard || (enabled(process.env.MAS_RATE_LIMIT_ENABLED)
    ? createMongoRequestGuard() : { async check() {}, async close() {} });
  const budget = masBudget || (enabled(process.env.MAS_BUDGET_ENABLED)
    ? createMongoMasBudget() : {
      async reserve() { return { reserveUsd: 0 }; }, async settle() {}, async close() {},
    });

  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, "http://127.0.0.1");

      if (req.method === "GET" && url.pathname === "/healthz") {
        return send(res, 200, { status: "ok" });
      }

      const identity = url.pathname.startsWith("/api/")
        ? requestIdentity(req, authOptions)
        : { userId: "anonymous", ip: "unknown" };

      const store = await storePromise;

      if (req.method === "POST" && url.pathname === "/api/rounds") {
        const payload = await readJson(req);
        const excluded = Array.isArray(payload.excludeRoundIds) ? payload.excludeRoundIds : [];
        return send(res, 201, serializeRound(await store.create(excluded, identity.userId)));
      }

      const roundMatch = url.pathname.match(/^\/api\/rounds\/([0-9a-f-]+)$/i);
      if (req.method === "GET" && roundMatch) {
        const round = await store.get(roundMatch[1], identity.userId);
        return round
          ? send(res, 200, serializeRound(round))
          : send(res, 404, { error: "Training round not found." });
      }

      const panoramaMatch = url.pathname.match(/^\/api\/rounds\/([0-9a-f-]+)\/panorama$/i);
      if (req.method === "GET" && panoramaMatch) {
        const round = await store.get(panoramaMatch[1], identity.userId);
        if (!round) return send(res, 404, { error: "Training round not found." });
        return send(res, 200, await fs.readFile(round.panorama.panoramaPath), "image/jpeg");
      }

      const viewMatch = url.pathname.match(/^\/api\/rounds\/([0-9a-f-]+)\/views\/(0|90|180|270)$/i);
      if (req.method === "GET" && viewMatch) {
        const round = await store.get(viewMatch[1], identity.userId);
        if (!round) return send(res, 404, { error: "Training round not found." });
        return send(res, 200, await fs.readFile(round.panorama.views[Number(viewMatch[2])]), "image/jpeg");
      }

      const guessMatch = url.pathname.match(/^\/api\/rounds\/([0-9a-f-]+)\/guess$/i);
      if (req.method === "POST" && guessMatch) {
        const payload = await readJson(req);
        const outcome = await store.guess(guessMatch[1], payload.countryIso2, identity.userId);
        return send(res, outcome.status, outcome.body);
      }

      const analyzeMatch = url.pathname.match(/^\/api\/rounds\/([0-9a-f-]+)\/analyze$/i);
      if (req.method === "POST" && analyzeMatch) {
        const round = await store.get(analyzeMatch[1], identity.userId);
        if (!round) return send(res, 404, { error: "Training round not found." });
        await guard.check(identity);
        const cacheKey = visionAnalysisCacheKey(round.panorama);
        const persisted = await analysisStore.get(cacheKey);
        if (persisted) {
          return send(res, 200, { ...persisted, cached: true });
        }

        let task = inFlightAnalyses.get(cacheKey);
        if (!task) {
          task = (async () => {
            let reservation;
            let retryCharge = 0;
            let raw;
            let generated;
            try {
              raw = await semaphore.use(async () => {
                reservation = await budget.reserve();
                return analyzeWithTimeoutRetry(
                  analyzeFn,
                  visionMasRequest(round.panorama),
                  async () => { retryCharge = 0.5; },
                );
              });
              generated = browserSafeAnalysisPayload(raw);
            } catch (error) {
              if (reservation) await budget.settle(reservation, reservation.reserveUsd);
              throw error;
            }
            await budget.settle(reservation, retryCharge + boundedNumber(raw.costUsd, 0));
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
      send(res, error.status || 400, { error: error.message || "Request failed." },
        "application/json", error.headers || {});
    }
  });
  let resourcesClosed;
  server.activeChildren = activeChildren;
  server.closeResources = () => {
    if (!resourcesClosed) resourcesClosed = Promise.all([
      analysisStore.close?.(), guard.close?.(), budget.close?.(),
      storePromise.then((store) => store.close?.()).catch(() => undefined),
    ]);
    return resourcesClosed;
  };
  server.on("close", () => { void server.closeResources(); });
  return server;
}

async function shutdownServer(server, {
  graceMs = VISION_ANALYSIS_TERMINATION_GRACE_MS,
  log = console,
} = {}) {
  const children = [...(server.activeChildren || [])];
  for (const child of children) {
    try { child.kill("SIGTERM"); } catch (error) {
      log.error(`Vision MAS graceful shutdown request failed: ${error.message || error}`);
    }
  }
  const serverClosed = new Promise((resolve) => {
    server.close((error) => resolve(error || null));
  });
  const childrenClosed = Promise.all(children.map((child) => new Promise((resolve) => {
    child.once("close", resolve);
  })));
  let timer;
  const timedOut = await Promise.race([
    Promise.all([serverClosed, childrenClosed, server.closeResources?.()]).then(() => false),
    new Promise((resolve) => { timer = setTimeout(() => resolve(true), graceMs); }),
  ]);
  clearTimeout(timer);
  if (timedOut) {
    log.error(
      "LANGSMITH_OBSERVABILITY_FAILURE: shutdown exceeded the trace-cleanup grace; "
        + "forcing remaining MAS children to stop.",
    );
    for (const child of server.activeChildren || []) {
      try { child.kill("SIGKILL"); } catch (error) {
        log.error(`Vision MAS forced shutdown failed: ${error.message || error}`);
      }
    }
    server.closeAllConnections?.();
  }
  return !timedOut;
}

if (require.main === module) {
  const server = createAppServer().listen(PORT, HOST, () => {
    console.log(`GeoGuessr training frontend: http://${HOST}:${PORT}`);
    console.log(`Vision MAS Python: ${PYTHON}`);
  });

  let shuttingDown = false;
  const handleShutdown = async (signal) => {
    if (shuttingDown) return;
    shuttingDown = true;
    console.log(`${signal} received: allowing up to 15 seconds for traces and MongoDB cleanup.`);
    const graceful = await shutdownServer(server);
    process.exit(graceful ? 0 : 1);
  };
  process.on("SIGTERM", () => { void handleShutdown("SIGTERM"); });
  process.on("SIGINT", () => { void handleShutdown("SIGINT"); });
}

module.exports = {
  RoundStore,
  analyzeWithTimeoutRetry,
  browserSafeAnalysisPayload,
  createAppServer,
  createMongoAnalysisStore,
  createMongoMasBudget,
  createMongoRequestGuard,
  createMongoRoundStore,
  listMongoTrainingPanoramas,
  listPilotTrainingPanoramas,
  listTrainingPanoramas,
  loadStorageMigrationOverlay,
  mergeTrainingPanoramas,
  isWholeRunTimeout,
  resolvePythonExecutable,
  runVisionAnalysis,
  Semaphore,
  serializeRound,
  shutdownServer,
  visionMasRequest,
  visionAnalysisCacheKey,
};
