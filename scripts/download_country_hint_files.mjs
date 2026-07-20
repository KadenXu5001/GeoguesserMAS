#!/usr/bin/env node

import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { activeCountries, countryBlocks } from "./update_reference_clues.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_DEFINITION = path.join(ROOT, "data", "dataset_definitions", "worldwide_v2.json");
const DEFAULT_OUTPUT = path.join(ROOT, "countryhintsfiles");
const MAX_IMAGE_BYTES = 15 * 1024 * 1024;

// The country guides are sections inside GeoTips' regional pages; their map/navigation links jump
// to these sections rather than opening a separate country URL.
const REGION_PAGES = {
  Europe: "https://geotips.net/europe/",
  Asia: "https://geotips.net/asia/",
  "South America": "https://geotips.net/south-america/",
  Oceania: "https://geotips.net/oceania/",
  "North America": "https://geotips.net/north-america/",
  Africa: "https://geotips.net/africa/",
};

const SOURCE_COUNTRY_NAMES = {
  Netherlands: "The Netherlands",
  "United Kingdom": "The United Kingdom",
  "United States": "The United States of America",
};

function parseArgs(argv) {
  const options = {
    definition: DEFAULT_DEFINITION,
    output: DEFAULT_OUTPUT,
    country: null,
    embedImages: true,
    repairExisting: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--definition") options.definition = argv[++index];
    else if (arg === "--output") options.output = argv[++index];
    else if (arg === "--country") options.country = argv[++index];
    else if (arg === "--skip-images") options.embedImages = false;
    else if (arg === "--repair-existing") options.repairExisting = true;
    else throw new Error(`Unsupported option: ${arg}`);
  }
  return options;
}

function slug(value) {
  return value.normalize("NFKD").replace(/[^\w\s-]/g, "")
    .trim().toLowerCase().replace(/[\s_]+/g, "-");
}

function decodeHtml(value) {
  return value.replace(/&amp;/gi, "&").replace(/&quot;/gi, '"').replace(/&#0*39;|&apos;/gi, "'");
}

function absoluteImageUrl(value, sourceUrl) {
  try {
    const decoded = decodeHtml(value.trim());
    if (!/\.(?:avif|gif|jpe?g|png|webp)(?:[?#].*)?$/i.test(decoded)) return null;
    return new URL(decoded, sourceUrl).href;
  } catch {
    return null;
  }
}

function imageResources(html, sourceUrl) {
  const resources = [];
  for (const match of html.matchAll(/\b(?:src|data-src|href)=["']([^"']+)["']/gi)) {
    const url = absoluteImageUrl(match[1], sourceUrl);
    if (url) resources.push({ attributeValue: match[1], url });
  }
  return resources.filter((resource, index, items) => (
    items.findIndex((item) => item.url === resource.url) === index
  ));
}

function normalizeImageTags(html) {
  return html.replace(/<img\b[^>]*>/gi, (tag) => {
    const attribute = (name) => tag.match(new RegExp(`\\b${name}=["']([^"']+)["']`, "i"))?.[1];
    const source = attribute("data-src") || attribute("data-lazy-src") || attribute("src");
    if (!source) return tag;
    const cleaned = tag
      .replace(/\s+(?:src|data-src|data-lazy-src|srcset|data-srcset)=["'][^"']*["']/gi, "")
      .replace(/\s+loading=["']lazy["']/gi, "");
    return cleaned.replace(/^<img\b/i, `<img src="${source}"`);
  });
}

async function fetchResponse(url) {
  const response = await fetch(url, {
    headers: { "user-agent": "GeoGuessr-MAS offline country-page downloader/1.0" },
    signal: AbortSignal.timeout(60_000),
  });
  if (!response.ok) throw new Error(`Failed to fetch ${url}: HTTP ${response.status}`);
  return response;
}

async function fetchText(url) {
  return (await fetchResponse(url)).text();
}

async function mapLimit(items, limit, operation) {
  const output = new Array(items.length);
  let cursor = 0;
  async function worker() {
    while (cursor < items.length) {
      const index = cursor;
      cursor += 1;
      output[index] = await operation(items[index], index);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return output;
}

async function embedCountryImages(countryHtml, sourceUrl) {
  const resources = imageResources(countryHtml, sourceUrl);
  const downloads = await mapLimit(resources, 6, async (resource) => {
    try {
      const response = await fetchResponse(resource.url);
      const mimeType = String(response.headers.get("content-type") || "application/octet-stream").split(";")[0];
      if (!mimeType.startsWith("image/")) throw new Error(`unexpected content type ${mimeType}`);
      const bytes = Buffer.from(await response.arrayBuffer());
      if (!bytes.length || bytes.length > MAX_IMAGE_BYTES) throw new Error(`invalid image size ${bytes.length}`);
      return {
        ...resource,
        sha256: createHash("sha256").update(bytes).digest("hex"),
        bytes: bytes.length,
        dataUrl: `data:${mimeType};base64,${bytes.toString("base64")}`,
      };
    } catch (error) {
      return { ...resource, error: error.message };
    }
  });
  let embeddedHtml = countryHtml;
  for (const resource of downloads.filter((item) => item.dataUrl)) {
    embeddedHtml = embeddedHtml.split(resource.attributeValue).join(resource.dataUrl);
  }
  return {
    html: embeddedHtml,
    images: downloads.map(({ dataUrl: _dataUrl, attributeValue: _attributeValue, ...item }) => item),
  };
}

function completeHtml({ country, continent, sourceUrl, retrievedAt, countryHtml }) {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <base href="${sourceUrl}">
  <title>${country} country hints</title>
  <style>
    body { font: 16px/1.5 system-ui, sans-serif; margin: 2rem auto; max-width: 1000px; padding: 0 1rem; }
    img { height: auto; max-width: 100%; }
    .provenance { background: #f3f4f6; border: 1px solid #d1d5db; padding: 1rem; }
  </style>
</head>
<body>
  <h1>${country}</h1>
  <div class="provenance">
    <p><strong>Region:</strong> ${continent}</p>
    <p><strong>Original regional page:</strong> <a href="${sourceUrl}">${sourceUrl}</a></p>
    <p><strong>Retrieved:</strong> ${retrievedAt}</p>
    <p>This file contains the complete country section extracted from its regional guide page.</p>
  </div>
  <main>${normalizeImageTags(countryHtml)}</main>
</body>
</html>
`;
}

async function repairExistingFiles(outputDir) {
  const manifestPath = path.join(outputDir, "manifest.json");
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  for (const item of manifest.files) {
    const target = path.join(outputDir, item.file);
    const original = await readFile(target, "utf8");
    const repaired = normalizeImageTags(original);
    await writeFile(target, repaired, "utf8");
    item.sha256 = createHash("sha256").update(repaired).digest("hex");
  }
  manifest.repaired_at = new Date().toISOString();
  manifest.image_markup = "eager-src-v1";
  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  console.log(`Repaired image markup in ${manifest.files.length} country files under ${outputDir}`);
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const definitionPath = path.resolve(options.definition);
  const outputDir = path.resolve(options.output);
  if (options.repairExisting) {
    await repairExistingFiles(outputDir);
    return;
  }
  const definitionBytes = await readFile(definitionPath);
  const definition = JSON.parse(definitionBytes.toString("utf8"));
  let countries = activeCountries(definition, "reference_generation");
  if (options.country) {
    const requested = options.country.toLowerCase();
    countries = countries.filter((item) => (
      item.country.toLowerCase() === requested || item.iso2.toLowerCase() === requested
    ));
    if (!countries.length) throw new Error(`Country is not active for reference generation: ${options.country}`);
  }
  await mkdir(outputDir, { recursive: true });
  const retrievedAt = new Date().toISOString();
  const regionalHtml = new Map();
  const sources = [];
  for (const continent of new Set(countries.map((item) => item.continent))) {
    const sourceUrl = REGION_PAGES[continent];
    if (!sourceUrl) throw new Error(`No regional guide page configured for ${continent}`);
    const html = await fetchText(sourceUrl);
    regionalHtml.set(continent, html);
    sources.push({
      continent,
      url: sourceUrl,
      retrieved_at: retrievedAt,
      sha256: createHash("sha256").update(html).digest("hex"),
    });
  }

  const files = [];
  for (const [index, country] of countries.entries()) {
    const sourceUrl = REGION_PAGES[country.continent];
    const sourceName = SOURCE_COUNTRY_NAMES[country.country] || country.country;
    const countryHtml = countryBlocks(regionalHtml.get(country.continent)).get(sourceName);
    if (!countryHtml) throw new Error(`Regional page does not contain ${country.country}`);
    const embedded = options.embedImages
      ? await embedCountryImages(countryHtml, sourceUrl)
      : { html: countryHtml, images: imageResources(countryHtml, sourceUrl).map((item) => ({ url: item.url })) };
    const document = completeHtml({
      country: country.country,
      continent: country.continent,
      sourceUrl,
      retrievedAt,
      countryHtml: embedded.html,
    });
    const filename = `${country.iso2.toLowerCase()}-${slug(country.country)}.html`;
    await writeFile(path.join(outputDir, filename), document, "utf8");
    files.push({
      iso2: country.iso2,
      country: country.country,
      continent: country.continent,
      file: filename,
      sha256: createHash("sha256").update(document).digest("hex"),
      image_count: embedded.images.length,
      image_failures: embedded.images.filter((item) => item.error),
    });
    console.log(`Wrote ${index + 1}/${countries.length}: ${filename}`);
  }

  const manifest = {
    schema_version: 1,
    retrieved_at: retrievedAt,
    definition: path.relative(ROOT, definitionPath).replaceAll("\\", "/"),
    definition_sha256: createHash("sha256").update(definitionBytes).digest("hex"),
    source_site: "GeoTips regional country guides",
    images_embedded: options.embedImages,
    image_markup: "eager-src-v1",
    country_count: files.length,
    sources,
    files,
  };
  await writeFile(path.join(outputDir, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  console.log(`Wrote ${files.length} ${options.embedImages ? "self-contained" : "remote-image"} country files to ${outputDir}`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}

export { absoluteImageUrl, completeHtml, imageResources, normalizeImageTags, slug };
