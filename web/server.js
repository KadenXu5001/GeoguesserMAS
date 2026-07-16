const http = require("node:http");
const path = require("node:path");
const os = require("node:os");
const fs = require("node:fs/promises");
const { spawn } = require("node:child_process");

const ROOT = path.resolve(__dirname, "..");
const PORT = Number(process.env.VISION_PORT || 3000);
const PYTHON = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const HEADINGS = [0, 90, 180, 270];

function send(res, status, body, type = "application/json") {
  res.writeHead(status, { "content-type": `${type}; charset=utf-8`, "cache-control": "no-store" });
  res.end(type === "application/json" ? JSON.stringify(body) : body);
}

async function readJson(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > 45 * 1024 * 1024) throw new Error("The upload is larger than 45 MB.");
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

async function listPanoramas() {
  const rows = [];
  for (const split of ["dev_v1", "eval_c1"]) {
    const text = await fs.readFile(path.join(ROOT, "data", "datasets", `${split}.csv`), "utf8");
    const [header, ...lines] = text.trim().split(/\r?\n/);
    const columns = header.split(",");
    for (const line of lines) {
      const values = line.split(",");
      const row = Object.fromEntries(columns.map((key, i) => [key, values[i]]));
      rows.push({
        id: row.mapillary_image_id,
        country: row.country,
        countryIso2: row.country_iso2,
        split: row.split,
        views: Object.fromEntries(HEADINGS.map((heading) => [heading, row[`view_h${String(heading).padStart(3, "0")}_path`]])),
      });
    }
  }
  return rows;
}

async function serveFrontend(res, requestPath) {
  const distRoot = path.join(__dirname, "dist");
  const file = requestPath === "/" ? "index.html" : requestPath.slice(1);
  const target = path.resolve(distRoot, file);
  if (!target.startsWith(`${distRoot}${path.sep}`)) return false;
  try {
    const content = await fs.readFile(target);
    const type = target.endsWith(".js") ? "text/javascript" : target.endsWith(".css") ? "text/css" : "text/html";
    send(res, 200, content, type);
    return true;
  } catch {
    if (requestPath !== "/") {
      const content = await fs.readFile(path.join(distRoot, "index.html"));
      send(res, 200, content, "text/html");
      return true;
    }
    return false;
  }
}

function resolveRepoPath(relativePath) {
  const resolved = path.resolve(ROOT, relativePath);
  if (!resolved.startsWith(`${ROOT}${path.sep}`)) throw new Error("Image path is outside the repository.");
  return resolved;
}

async function analyze(payload) {
  if (!payload || !Array.isArray(payload.paths) || payload.paths.length !== 4) {
    throw new Error("Choose one MAS panorama before analyzing.");
  }
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "geoguesser-vision-"));
  try {
    const paths = payload.paths.map(resolveRepoPath);
    const input = JSON.stringify({ paths, model: "gemini-3-flash-preview" });
    return await new Promise((resolve, reject) => {
      const child = spawn(PYTHON, [path.join(ROOT, "scripts", "run_vision_bbox.py")], {
        cwd: ROOT,
        env: { ...process.env, PYTHONPATH: path.join(ROOT, "src") },
        stdio: ["pipe", "pipe", "pipe"],
      });
      let stdout = ""; let stderr = "";
      child.stdout.on("data", (chunk) => { stdout += chunk; });
      child.stderr.on("data", (chunk) => { stderr += chunk; });
      child.on("error", reject);
      child.on("close", (code) => code === 0 ? resolve(JSON.parse(stdout)) : reject(new Error(stderr || `Vision process exited with ${code}.`)));
      child.stdin.end(input);
    });
  } finally {
    await fs.rm(tempDir, { recursive: true, force: true });
  }
}

const server = http.createServer(async (req, res) => {
  try {
    if (req.method === "GET" && req.url === "/api/panoramas") return send(res, 200, await listPanoramas());
    if (req.method === "GET" && req.url.startsWith("/media?path=")) {
      const relativePath = decodeURIComponent(req.url.slice("/media?path=".length));
      const file = resolveRepoPath(relativePath);
      return send(res, 200, await fs.readFile(file), "image/jpeg");
    }
    if (req.method === "POST" && req.url === "/api/analyze") return send(res, 200, await analyze(await readJson(req)));
    if (req.method === "GET" && await serveFrontend(res, req.url)) return;
    send(res, 404, { error: "Not found" });
  } catch (error) {
    send(res, 400, { error: error.message || "Request failed." });
  }
});

server.listen(PORT, "127.0.0.1", () => console.log(`Vision inspector: http://localhost:${PORT}`));
