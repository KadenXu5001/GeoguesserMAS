const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { createAppServer } = require("../server");

async function startFixture() {
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
    }],
    randomIndex: () => 0,
    analyze: async () => {
      analyzeCalls += 1;
      return { signs_and_language: { objects: [] } };
    },
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
