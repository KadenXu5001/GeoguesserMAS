const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const {
  analyzeWithTransientRetry,
  createAppServer,
  isRetryableVisionError,
  listTrainingPanoramas,
  resolvePythonExecutable,
  visionMasRequest,
  visionAnalysisCacheKey,
} = require("../server");

function memoryAnalysisStore(documents = new Map()) {
  return {
    async get(key) { return documents.get(key) || null; },
    async set(key, payload) { documents.set(key, structuredClone(payload)); },
    async close() {},
  };
}

test("website MAS prefers the populated project runtime over PATH python", () => {
  const root = path.join("C:", "project");
  const expected = path.join(root, ".runtime-win", "Scripts", "python.exe");
  const resolved = resolvePythonExecutable({
    root,
    env: {},
    platform: "win32",
    existsSync: (candidate) => candidate === expected,
  });

  assert.equal(resolved, expected);
});

test("website MAS honors an explicit PYTHON override", () => {
  assert.equal(
    resolvePythonExecutable({
      root: "unused",
      env: { PYTHON: "C:\\custom\\python.exe" },
      platform: "win32",
      existsSync: () => false,
    }),
    "C:\\custom\\python.exe",
  );
});

test("website MAS request preserves object-store identity and cardinal order", () => {
  const request = visionMasRequest({
    sourceId: "image-1",
    datasetVersion: "pilot_v1",
    views: { 270: "h270.jpg", 0: "h000.jpg", 180: "h180.jpg", 90: "h090.jpg" },
    viewHashes: { 270: "d", 0: "a", 180: "c", 90: "b" },
  });

  assert.deepEqual(request, {
    imageId: "image-1",
    datasetVersion: "pilot_v1",
    paths: ["h000.jpg", "h090.jpg", "h180.jpg", "h270.jpg"],
    viewHashes: ["a", "b", "c", "d"],
  });
});

test("website MAS retry classification is limited to transient transport and capacity errors", () => {
  assert.equal(isRetryableVisionError(new Error("httpx.ReadTimeout: read timed out")), true);
  assert.equal(isRetryableVisionError(Object.assign(new Error("quota"), { status: 429 })), true);
  assert.equal(isRetryableVisionError(new Error("ExtractionOutput validation failed")), false);
});

test("website starts exactly one fresh MAS run after a transient failure", async () => {
  let attempts = 0;
  const request = { paths: ["0.jpg", "90.jpg", "180.jpg", "270.jpg"] };
  const result = await analyzeWithTransientRetry(async (received) => {
    attempts += 1;
    assert.equal(received, request);
    if (attempts === 1) throw new Error("httpx.WriteTimeout: The write operation timed out");
    return { analysis: {}, informedEvidence: [] };
  }, request);

  assert.equal(attempts, 2);
  assert.deepEqual(result, { analysis: {}, informedEvidence: [] });
});

test("website does not retry a deterministic MAS failure", async () => {
  let attempts = 0;
  await assert.rejects(
    analyzeWithTransientRetry(async () => {
      attempts += 1;
      throw new Error("ExtractionOutput validation failed");
    }, {}),
    /validation failed/,
  );
  assert.equal(attempts, 1);
});

test("website stops after the second transient MAS failure", async () => {
  let attempts = 0;
  await assert.rejects(
    analyzeWithTransientRetry(async () => {
      attempts += 1;
      throw new Error("503 UNAVAILABLE");
    }, {}),
    /503 UNAVAILABLE/,
  );
  assert.equal(attempts, 2);
});

async function startFixture({ analysisStore = memoryAnalysisStore(), analyze } = {}) {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "atlaslens-server-test-"));
  const panoramaPath = path.join(directory, "secret-brazil-panorama.jpg");
  const viewPaths = Object.fromEntries([0, 90, 180, 270].map((heading) => [
    heading,
    path.join(directory, `secret-br-${heading}.jpg`),
  ]));
  await Promise.all([
    fs.writeFile(panoramaPath, Buffer.from("panorama-bytes")),
    ...Object.values(viewPaths).map((target) => fs.writeFile(target, Buffer.from("view-bytes"))),
  ]);
  let analyzeCalls = 0;
  const server = createAppServer({
    panoramas: [{
      sourceId: "mapillary-secret-123",
      countryIso2: "BR",
      country: "Brazil",
      panoramaPath,
      views: viewPaths,
      viewHashes: Object.fromEntries([0, 90, 180, 270].map((heading) => [
        heading,
        `hash-${heading}`,
      ])),
    }],
    randomIndex: () => 0,
    analysisStore,
    analyze: analyze || (async () => {
      analyzeCalls += 1;
      return {
        analysis: { signs_and_language: { objects: [] } },
        informedEvidence: [{
          id: "informed-1",
          description: "Portuguese road text supports Brazil.",
          observation: "Portuguese road text",
          heading: 0,
          bbox: { ymin: 10, xmin: 20, ymax: 100, xmax: 200 },
        }],
      };
    }),
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  return {
    baseUrl: `http://127.0.0.1:${address.port}`,
    server,
    directory,
    getAnalyzeCalls: () => analyzeCalls,
  };
}

async function jsonRequest(url, options = {}) {
  const response = await fetch(url, options);
  return { response, body: await response.json() };
}

test("round payload hides answer-bearing metadata until submission", async (t) => {
  const fixture = await startFixture();
  t.after(async () => {
    await new Promise((resolve) => fixture.server.close(resolve));
    await fs.rm(fixture.directory, { recursive: true, force: true });
  });

  const created = await jsonRequest(`${fixture.baseUrl}/api/rounds`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ excludeRoundIds: [] }),
  });
  assert.equal(created.response.status, 201);
  assert.match(created.body.roundId, /^[0-9a-f-]{36}$/);
  const serialized = JSON.stringify(created.body).toLowerCase();
  for (const secret of ["brazil", "mapillary-secret", "secret-br", "secret-brazil", "countryiso2"]) {
    assert.equal(serialized.includes(secret), false, `pre-guess payload leaked ${secret}`);
  }

  const panorama = await fetch(`${fixture.baseUrl}${created.body.panoramaUrl}`);
  assert.equal(panorama.status, 200);
  assert.equal(await panorama.text(), "panorama-bytes");

  const wrong = await jsonRequest(`${fixture.baseUrl}/api/rounds/${created.body.roundId}/guess`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ countryIso2: "CA" }),
  });
  assert.equal(wrong.response.status, 200);
  assert.equal(wrong.body.correct, false);
  assert.deepEqual(wrong.body.correctCountry, { iso2: "BR", name: "Brazil" });
  assert.equal(wrong.body.selectedCountry.iso2, "CA");

  const repeated = await jsonRequest(`${fixture.baseUrl}/api/rounds/${created.body.roundId}/guess`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ countryIso2: "BR" }),
  });
  assert.equal(repeated.response.status, 409);
});

test("vision analysis is generated once and reused per panorama", async (t) => {
  const fixture = await startFixture();
  t.after(async () => {
    await new Promise((resolve) => fixture.server.close(resolve));
    await fs.rm(fixture.directory, { recursive: true, force: true });
  });
  const created = await jsonRequest(`${fixture.baseUrl}/api/rounds`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: "{}",
  });
  const endpoint = `${fixture.baseUrl}/api/rounds/${created.body.roundId}/analyze`;
  const first = await jsonRequest(endpoint, { method: "POST" });
  const second = await jsonRequest(endpoint, { method: "POST" });
  assert.equal(first.body.cached, false);
  assert.equal(second.body.cached, true);
  assert.equal(fixture.getAnalyzeCalls(), 1);
  assert.deepEqual(second.body.analysis, first.body.analysis);
  assert.deepEqual(second.body.informedEvidence, first.body.informedEvidence);
  const serialized = JSON.stringify(second.body).toLowerCase();
  assert.equal(serialized.includes('"country"'), false);
  assert.equal(serialized.includes('"alternatives"'), false);
});

test("persistent website cache survives a server restart without invoking MAS", async (t) => {
  const documents = new Map();
  const firstFixture = await startFixture({ analysisStore: memoryAnalysisStore(documents) });
  const firstRound = await jsonRequest(`${firstFixture.baseUrl}/api/rounds`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: "{}",
  });
  const first = await jsonRequest(
    `${firstFixture.baseUrl}/api/rounds/${firstRound.body.roundId}/analyze`,
    { method: "POST" },
  );
  assert.equal(first.body.cached, false);
  assert.equal(firstFixture.getAnalyzeCalls(), 1);
  await new Promise((resolve) => firstFixture.server.close(resolve));
  await fs.rm(firstFixture.directory, { recursive: true, force: true });

  const secondFixture = await startFixture({
    analysisStore: memoryAnalysisStore(documents),
    analyze: async () => { throw new Error("MAS must not run on a persistent cache hit"); },
  });
  t.after(async () => {
    await new Promise((resolve) => secondFixture.server.close(resolve));
    await fs.rm(secondFixture.directory, { recursive: true, force: true });
  });
  const secondRound = await jsonRequest(`${secondFixture.baseUrl}/api/rounds`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: "{}",
  });
  const second = await jsonRequest(
    `${secondFixture.baseUrl}/api/rounds/${secondRound.body.roundId}/analyze`,
    { method: "POST" },
  );
  assert.equal(second.response.status, 200);
  assert.equal(second.body.cached, true);
  assert.deepEqual(second.body.analysis, first.body.analysis);
});

test("failed vision analysis is not persisted", async (t) => {
  const documents = new Map();
  let attempts = 0;
  const fixture = await startFixture({
    analysisStore: memoryAnalysisStore(documents),
    analyze: async () => {
      attempts += 1;
      if (attempts === 1) throw new Error("temporary provider failure");
      return { analysis: { infrastructure: { objects: [] } }, informedEvidence: [] };
    },
  });
  t.after(async () => {
    await new Promise((resolve) => fixture.server.close(resolve));
    await fs.rm(fixture.directory, { recursive: true, force: true });
  });
  const created = await jsonRequest(`${fixture.baseUrl}/api/rounds`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: "{}",
  });
  const endpoint = `${fixture.baseUrl}/api/rounds/${created.body.roundId}/analyze`;
  const failed = await jsonRequest(endpoint, { method: "POST" });
  const recovered = await jsonRequest(endpoint, { method: "POST" });
  assert.equal(failed.response.status, 400);
  assert.equal(recovered.response.status, 200);
  assert.equal(recovered.body.cached, false);
  assert.equal(attempts, 2);
  assert.equal(documents.size, 1);
});

test("vision cache identity changes when a rendered view changes", () => {
  const panorama = {
    sourceId: "image-1",
    viewHashes: { 0: "a", 90: "b", 180: "c", 270: "d" },
  };
  const first = visionAnalysisCacheKey(panorama);
  panorama.viewHashes[270] = "changed";
  assert.notEqual(visionAnalysisCacheKey(panorama), first);
});

test("static GeoJSON is served as a feature collection instead of a serialized buffer", async (t) => {
  const fixture = await startFixture();
  t.after(async () => {
    await new Promise((resolve) => fixture.server.close(resolve));
    await fs.rm(fixture.directory, { recursive: true, force: true });
  });

  const response = await fetch(`${fixture.baseUrl}/countries.geojson`);
  const data = await response.json();

  assert.equal(response.status, 200);
  assert.equal(data.type, "FeatureCollection");
  assert.ok(data.features.length > 0);
  assert.equal(data.type === "Buffer", false);
});

test("training media resolves through a completed object-store migration overlay", async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "atlaslens-migration-test-"));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const datasetDir = path.join(root, "data", "datasets");
  const migrationDir = path.join(root, "data", "migrations");
  const objectDir = path.join(root, ".local-data", "source-private", "countries", "FR");
  const runtimeDir = path.join(root, ".local-data", "runtime-private", "countries", "FR");
  await Promise.all([
    fs.mkdir(datasetDir, { recursive: true }),
    fs.mkdir(migrationDir, { recursive: true }),
    fs.mkdir(objectDir, { recursive: true }),
    fs.mkdir(runtimeDir, { recursive: true }),
  ]);
  const panorama = path.join(objectDir, "panorama.jpg");
  const views = Object.fromEntries([0, 90, 180, 270].map((heading) => [
    heading,
    path.join(runtimeDir, `h${heading}.jpg`),
  ]));
  await Promise.all([
    fs.writeFile(panorama, "panorama"),
    ...Object.values(views).map((target) => fs.writeFile(target, "view")),
  ]);
  const headers = [
    "mapillary_image_id", "country_iso2", "country", "panorama_path",
    "panorama_width", "panorama_height", "view_h000_path", "view_h000_sha256",
    "view_h090_path", "view_h090_sha256", "view_h180_path", "view_h180_sha256",
    "view_h270_path", "view_h270_sha256",
  ];
  const values = [
    "image-1", "FR", "France", "missing-legacy.jpg", "400", "200",
    "missing-0.jpg", "hash-0", "missing-90.jpg", "hash-90",
    "missing-180.jpg", "hash-180", "missing-270.jpg", "hash-270",
  ];
  await fs.writeFile(
    path.join(datasetDir, "dev_v1.csv"),
    `${headers.join(",")}\n${values.join(",")}\n`,
  );
  await fs.writeFile(path.join(datasetDir, "eval_c1.csv"), `${headers.join(",")}\n`);
  await fs.writeFile(
    path.join(migrationDir, "pilot_v1_object_store.json"),
    JSON.stringify({
      status: "complete",
      dataset_version: "pilot_v1",
      items: [{
        provider_image_id: "image-1",
        panorama_object_store_path: path.relative(root, panorama),
        view_object_store_paths: Object.fromEntries(
          Object.entries(views).map(([heading, target]) => [heading, path.relative(root, target)]),
        ),
      }],
    }),
  );

  const panoramas = await listTrainingPanoramas(root);

  assert.equal(panoramas.length, 1);
  assert.equal(panoramas[0].panoramaPath, panorama);
  assert.equal(panoramas[0].views[270], views[270]);
});
