const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { createAppServer, visionAnalysisCacheKey } = require("../server");

function memoryAnalysisStore(documents = new Map()) {
  return {
    async get(key) { return documents.get(key) || null; },
    async set(key, payload) { documents.set(key, structuredClone(payload)); },
    async close() {},
  };
}

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
