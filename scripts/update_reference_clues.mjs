#!/usr/bin/env node

import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_DEFINITION = path.join(ROOT, "data", "dataset_definitions", "worldwide_v2.json");
const DEFAULT_SNAPSHOT = path.join(ROOT, "data", "reference_tables", "reference_v1.json");
const DEFAULT_MODEL = "gemini-3.5-flash";
const MAX_IMAGE_BYTES = 15 * 1024 * 1024;
const DEFAULT_MAX_IMAGES = 1200;
const PROMPT_VERSION = "geotips-visible-clue-v1";

const GEOTIPS_PAGES = {
  Europe: "https://geotips.net/europe/",
  Asia: "https://geotips.net/asia/",
  "South America": "https://geotips.net/south-america/",
  Oceania: "https://geotips.net/oceania/",
  "North America": "https://geotips.net/north-america/",
  Africa: "https://geotips.net/africa/",
};

const GEOTIPS_COUNTRY_NAMES = {
  Netherlands: "The Netherlands",
  "United Kingdom": "The United Kingdom",
  "United States": "The United States of America",
};

const UNSUPPORTED_SECTION_PATTERNS = [
  /country flag/i,
  /capital city/i,
  /most helpful/i,
  /google car/i,
  /rare car/i,
  /follow car/i,
  /google coverage/i,
  /camera generation/i,
  /subdivisions?/i,
];

// One GeoTips section can be useful to more than one specialist. Each target is an existing,
// constitution-approved lookup category; unsupported sections are reported instead of invented.
const SECTION_RULES = [
  { match: /driving side/i, targets: [["universal", "driving_side"]] },
  { match: /license plates?/i, targets: [["universal", "license_plates"]] },
  { match: /road (?:lines?|markings?)/i, targets: [["universal", "road_markings"]] },
  { match: /road layout/i, targets: [["universal", "road_markings"]] },
  { match: /(?:alphabet|script|language)/i, targets: [["universal", "language_script"]] },
  { match: /domain/i, targets: [["universal", "country_domains"]] },
  { match: /bollards?|kilomet(?:er|re) markers?/i, targets: [["universal", "bollards"]] },
  { match: /chevrons?|guardrails?|sign backs?/i, targets: [["universal", "chevrons_guardrails"]] },
  {
    match: /(?:unique|rare) vehicles?|unique taxis?|taxi colou?rs?/i,
    targets: [["universal", "vehicles"], ["urban", "public_transit"]],
  },
  {
    match: /public (?:transport|transit)|buses|trams/i,
    targets: [["urban", "public_transit"]],
  },
  {
    match: /street (?:sign|name)|town names?|addresses?/i,
    targets: [["urban", "street_names_addresses"], ["urban", "urban_signage"]],
  },
  {
    match: /road signs?|highway signs?|road numbering|guide to understanding signs/i,
    targets: [["urban", "urban_signage"], ["rural", "rural_roadside_features"]],
  },
  {
    match: /electricity poles?|utility poles?/i,
    targets: [["urban", "urban_utility_poles"], ["rural", "rural_utility_poles"]],
  },
  {
    match: /architecture|buildings?|houses?/i,
    targets: [["urban", "urban_architecture"], ["rural", "rural_architecture"]],
  },
  {
    match: /phone (?:numbers?|area codes?)|currency|business(?:es)?|companies|ads/i,
    targets: [["urban", "businesses_domains"]],
  },
  { match: /sidewalks?|curbs?|kerbs?/i, targets: [["urban", "sidewalks_curbs"]] },
  {
    match: /vegetation|landscape|regional plants?|specific plants?|specific trees?/i,
    targets: [["rural", "vegetation_biomes"], ["rural", "terrain_scenery"]],
  },
  { match: /general look|terrain|scenery/i, targets: [["rural", "terrain_scenery"]] },
  { match: /topography/i, targets: [["rural", "terrain_scenery"]] },
  { match: /highways?/i, targets: [["rural", "rural_roadside_features"]] },
  { match: /climate|weather/i, targets: [["rural", "climate"]] },
  { match: /agriculture|crops?|farms?|land use/i, targets: [["rural", "agriculture_land_use"]] },
  { match: /soil|geology/i, targets: [["rural", "soil_geology"]] },
];

function parseArgs(argv) {
  const options = {
    definition: DEFAULT_DEFINITION,
    snapshot: DEFAULT_SNAPSHOT,
    analyzeImages: false,
    dryRun: false,
    country: null,
    maxImages: DEFAULT_MAX_IMAGES,
    model: process.env.GEMINI_REFERENCE_MODEL || DEFAULT_MODEL,
  };
  const positional = [];
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--analyze-images") options.analyzeImages = true;
    else if (arg === "--dry-run") options.dryRun = true;
    else if (arg === "--definition") options.definition = argv[++index];
    else if (arg === "--snapshot") options.snapshot = argv[++index];
    else if (arg === "--country") options.country = argv[++index];
    else if (arg === "--max-images") options.maxImages = Number(argv[++index]);
    else if (arg === "--model") options.model = argv[++index];
    else if (arg.startsWith("--")) throw new Error(`Unsupported option: ${arg}`);
    else positional.push(arg);
  }
  if (positional[0]) options.definition = positional[0];
  if (positional[1]) options.snapshot = positional[1];
  if (!Number.isInteger(options.maxImages) || options.maxImages < 0) {
    throw new Error("--max-images must be a non-negative integer");
  }
  return options;
}

async function loadDotEnv() {
  try {
    const text = await readFile(path.join(ROOT, ".env"), "utf8");
    for (const line of text.split(/\r?\n/)) {
      const match = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/);
      if (!match || process.env[match[1]]) continue;
      let value = match[2];
      if ((value.startsWith('"') && value.endsWith('"'))
        || (value.startsWith("'") && value.endsWith("'"))) value = value.slice(1, -1);
      process.env[match[1]] = value;
    }
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
}

function decodeHtml(value) {
  const entities = {
    amp: "&", apos: "'", gt: ">", lt: "<", nbsp: " ", quot: '"',
    ndash: "–", mdash: "—", rsquo: "’", lsquo: "‘", rdquo: "”", ldquo: "“",
  };
  return value
    .replace(/&#(\d+);/g, (_, code) => String.fromCodePoint(Number(code)))
    .replace(/&#x([0-9a-f]+);/gi, (_, code) => String.fromCodePoint(Number.parseInt(code, 16)))
    .replace(/&([a-z]+);/gi, (match, name) => entities[name.toLowerCase()] ?? match);
}

function visibleText(html) {
  return decodeHtml(html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
    .replace(/<img\b[^>]*>/gi, " ")
    .replace(/<br\s*\/?>/gi, ". ")
    .replace(/<\/(?:p|li|h[1-6])\s*>/gi, ". ")
    .replace(/<[^>]+>/g, " "))
    .replace(/\bImage\b/gi, " ")
    .replace(/\s+/g, " ")
    .replace(/\s+([,.;:])/g, "$1")
    .replace(/\.{2,}/g, ".")
    .trim();
}

function normalizedHeading(value) {
  return value.replace(/\s+/g, " ").replace(/:$/, "").trim();
}

function countryBlocks(html) {
  const headings = [...html.matchAll(/<h2\b[^>]*>([\s\S]*?)<\/h2>/gi)].map((match) => ({
    country: visibleText(match[1]).replace(/\.$/, ""),
    start: match.index,
    contentStart: match.index + match[0].length,
  }));
  const countryHeadings = headings.filter((heading) => {
    const following = html.slice(heading.contentStart, heading.contentStart + 2500);
    return /Country\s*Flag/i.test(visibleText(following));
  });
  return new Map(countryHeadings.map((heading, index) => [
    heading.country,
    html.slice(heading.contentStart, countryHeadings[index + 1]?.start ?? html.length),
  ]));
}

function sectionBodies(block) {
  const headings = [...block.matchAll(/<h4\b[^>]*>([\s\S]*?)<\/h4>/gi)].map((match) => ({
    heading: normalizedHeading(visibleText(match[1])),
    start: match.index,
    contentStart: match.index + match[0].length,
  }));
  return headings.map((heading, index) => ({
    heading: heading.heading,
    body: block.slice(heading.contentStart, headings[index + 1]?.start ?? block.length),
  }));
}

function targetsForHeading(heading) {
  if (UNSUPPORTED_SECTION_PATTERNS.some((pattern) => pattern.test(heading))) return [];
  return SECTION_RULES.flatMap((rule) => (rule.match.test(heading) ? rule.targets : []))
    .filter((target, index, targets) => targets.findIndex((item) => item.join(":") === target.join(":")) === index);
}

function compactIndicator(html, limit = 700) {
  const rawText = visibleText(html).replace(/^\s*[-–—:]+\s*/, "").trim();
  const usable = (rawText.match(/[^.!?]+[.!?]+|[^.!?]+$/g) ?? [])
    .map((sentence) => sentence.trim())
    .filter((sentence) => !/\b(?:google (?:car|coverage)|street view|camera generation|gen [234]|coverage)\b/i.test(sentence))
    .filter((sentence) => !/\b(?:above|below|image|picture|photo|on the map)\b/i.test(sentence));
  const text = usable.join(" ").trim();
  if (text.length <= limit) return text;
  const clipped = text.slice(0, limit - 1);
  return `${clipped.slice(0, Math.max(80, clipped.lastIndexOf(" ")))}…`;
}

function absoluteUrl(value, sourceUrl) {
  try {
    const decoded = decodeHtml(value.trim());
    if (!/\.(?:avif|gif|jpe?g|png|webp)(?:\?|$)/i.test(decoded)) return null;
    return new URL(decoded, sourceUrl).href;
  } catch {
    return null;
  }
}

function extractImageUrls(html, sourceUrl) {
  const anchorUrls = [...html.matchAll(/<a\b[^>]*\bhref=["']([^"']+)["'][^>]*>/gi)]
    .map((match) => absoluteUrl(match[1], sourceUrl)).filter(Boolean);
  const imageUrls = [...html.matchAll(/<img\b[^>]*(?:\bdata-src|\bsrc)=["']([^"']+)["'][^>]*>/gi)]
    .map((match) => absoluteUrl(match[1], sourceUrl)).filter(Boolean);
  return [...new Set(anchorUrls.length ? anchorUrls : imageUrls)];
}

function activeCountries(definition, scope = "reference_generation") {
  const excluded = new Set((definition.temporary_exclusions || [])
    .filter((item) => Array.isArray(item.scopes) && item.scopes.includes(scope))
    .map((item) => String(item.iso2).toUpperCase()));
  return definition.countries.filter((country) => !excluded.has(String(country.iso2).toUpperCase()));
}

function sourceSectionsForCountry(country, html, sourceUrl) {
  const sourceCountry = GEOTIPS_COUNTRY_NAMES[country] || country;
  const block = countryBlocks(html).get(sourceCountry);
  if (!block) throw new Error(`GeoTips page does not contain a country block for ${country}`);
  return sectionBodies(block).map((section) => ({
    ...section,
    targets: targetsForHeading(section.heading),
    text: compactIndicator(section.body),
    imageUrls: extractImageUrls(section.body, sourceUrl),
  }));
}

async function fetchResponse(url, options = {}) {
  const response = await fetch(url, {
    headers: { "user-agent": "GeoGuessr-MAS reference snapshot builder/2.0", ...options.headers },
    signal: AbortSignal.timeout(60_000),
    ...options,
  });
  if (!response.ok) throw new Error(`Failed to fetch ${url}: HTTP ${response.status}`);
  return response;
}

async function fetchPage(url) {
  return (await fetchResponse(url)).text();
}

async function downloadImage(url) {
  const response = await fetchResponse(url);
  const mimeType = String(response.headers.get("content-type") || "image/jpeg").split(";")[0];
  if (!mimeType.startsWith("image/")) throw new Error(`GeoTips image returned ${mimeType}: ${url}`);
  const bytes = Buffer.from(await response.arrayBuffer());
  if (!bytes.length || bytes.length > MAX_IMAGE_BYTES) {
    throw new Error(`GeoTips image has invalid size ${bytes.length}: ${url}`);
  }
  return { bytes, mimeType, sha256: createHash("sha256").update(bytes).digest("hex") };
}

function parseGeminiJson(text) {
  const cleaned = text.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  const value = JSON.parse(cleaned);
  if (!value || typeof value.description !== "string" || !value.description.trim()) {
    throw new Error("Gemini image response omitted description");
  }
  return value.description.trim().replace(/\s+/g, " ").slice(0, 320);
}

async function mapLimit(items, limit, operation) {
  const results = new Array(items.length);
  let cursor = 0;
  async function worker() {
    while (cursor < items.length) {
      const index = cursor;
      cursor += 1;
      results[index] = await operation(items[index], index);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return results;
}

function chunked(items, size) {
  return Array.from({ length: Math.ceil(items.length / size) }, (_, index) => (
    items.slice(index * size, (index + 1) * size)
  ));
}

async function analyzeImageBatch(items, { model, apiKey }) {
  const prompt = [
    `Inspect all ${items.length} images. Describe only visible, reusable GeoGuessr clues.`,
    "Do not identify a country from prior knowledge. Do not mention Google cars, cameras, coverage,",
    "image position, flags, watermarks, or facts that are not visually supported.",
    "Return JSON as {\"observations\":[{\"index\":1,\"description\":\"at most 30 words\"}]}",
    "with exactly one observation for every numbered image.",
  ].join(" ");
  const parts = [{ text: prompt }];
  for (const [index, item] of items.entries()) {
    parts.push({
      text: `IMAGE ${index + 1}; source section ${item.country} / ${item.heading}; categories ${item.targets.map((target) => target[1]).join(", ")}`,
    });
    parts.push({ inline_data: { mime_type: item.mimeType, data: item.bytes.toString("base64") } });
  }
  let response;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    response = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`,
      {
        method: "POST",
        headers: { "content-type": "application/json", "x-goog-api-key": apiKey },
        signal: AbortSignal.timeout(120_000),
        body: JSON.stringify({
          contents: [{ parts }],
          generationConfig: {
            responseMimeType: "application/json",
            responseJsonSchema: {
              type: "object",
              properties: {
                observations: {
                  type: "array",
                  minItems: items.length,
                  maxItems: items.length,
                  items: {
                    type: "object",
                    properties: {
                      index: { type: "integer" },
                      description: { type: "string" },
                    },
                    required: ["index", "description"],
                    additionalProperties: false,
                  },
                },
              },
              required: ["observations"],
              additionalProperties: false,
            },
            temperature: 0,
          },
        }),
      },
    );
    if (response.ok || ![429, 500, 502, 503, 504].includes(response.status) || attempt === 3) break;
    await new Promise((resolve) => setTimeout(resolve, attempt * 1500));
  }
  if (!response.ok) throw new Error(`Gemini ${model} failed: HTTP ${response.status} ${(await response.text()).slice(0, 300)}`);
  const body = await response.json();
  const raw = body.candidates?.[0]?.content?.parts?.map((part) => part.text || "").join("") || "";
  const cleaned = raw.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  const observations = JSON.parse(cleaned).observations;
  if (!Array.isArray(observations) || observations.length !== items.length) {
    throw new Error(`Gemini image batch returned ${observations?.length ?? 0}/${items.length} observations`);
  }
  const byIndex = new Map(observations.map((item) => [Number(item.index), item.description]));
  return items.map((_, index) => parseGeminiJson(JSON.stringify({ description: byIndex.get(index + 1) })));
}

function existingImageCache(snapshot, model) {
  const cache = new Map();
  for (const evidence of snapshot.enrichment?.image_analyses || []) {
    if (evidence.model === model && evidence.prompt_version === PROMPT_VERSION
      && evidence.sha256 && evidence.description) cache.set(evidence.sha256, evidence.description);
  }
  for (const row of snapshot.rows || []) {
    for (const evidence of row.image_evidence || []) {
      if (evidence.model === model && evidence.prompt_version === PROMPT_VERSION
        && evidence.sha256 && evidence.description) cache.set(evidence.sha256, evidence.description);
    }
  }
  return cache;
}

async function enrichImages(sections, snapshot, options) {
  const relevant = sections.filter((section) => section.targets.length);
  const urls = [...new Set(relevant.flatMap((section) => section.imageUrls))];
  if (urls.length > options.maxImages) {
    throw new Error(`Found ${urls.length} relevant GeoTips images, above --max-images ${options.maxImages}`);
  }
  if (!options.analyzeImages) return { imageCount: urls.length, uniqueImages: null, analyzed: 0, reused: 0, analyses: [] };
  await loadDotEnv();
  const apiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;
  if (!apiKey) throw new Error("--analyze-images requires GEMINI_API_KEY or GOOGLE_API_KEY");
  const cache = existingImageCache(snapshot, options.model);
  let downloadsComplete = 0;
  const downloadResults = await mapLimit(urls, 8, async (url) => {
    let image;
    try {
      image = await downloadImage(url);
    } catch (error) {
      return { url, error: error.message };
    }
    downloadsComplete += 1;
    if (downloadsComplete % 50 === 0 || downloadsComplete === urls.length) {
      console.log(`Downloaded and hashed ${downloadsComplete}/${urls.length} relevant images`);
    }
    return { url, ...image };
  });
  const imageFailures = downloadResults.filter((item) => item.error);
  const downloaded = downloadResults.filter((item) => !item.error);
  if (imageFailures.length) {
    console.warn(`Skipped ${imageFailures.length} unavailable GeoTips images; failures will be recorded`);
  }
  const firstByHash = new Map();
  for (const image of downloaded) {
    const section = relevant.find((item) => item.imageUrls.includes(image.url));
    if (!firstByHash.has(image.sha256)) firstByHash.set(image.sha256, { ...image, ...section });
  }
  const unique = [...firstByHash.values()];
  if (unique.length > options.maxImages) {
    throw new Error(`Found ${unique.length} unique relevant images, above --max-images ${options.maxImages}`);
  }
  const pending = unique.filter((item) => !cache.has(item.sha256));
  let batchesComplete = 0;
  const batches = chunked(pending, 6);
  const batchResults = await mapLimit(batches, 4, async (batch) => {
    const descriptions = await analyzeImageBatch(batch, { model: options.model, apiKey });
    batchesComplete += 1;
    const analyzedCount = Math.min(batchesComplete * 6, pending.length);
    if (batchesComplete % 5 === 0 || batchesComplete === batches.length) {
      console.log(`Gemini analyzed approximately ${analyzedCount}/${pending.length} uncached images`);
    }
    return descriptions;
  });
  for (const [batchIndex, batch] of batches.entries()) {
    for (const [itemIndex, item] of batch.entries()) {
      cache.set(item.sha256, batchResults[batchIndex][itemIndex]);
    }
  }
  const byUrl = new Map(downloaded.map((image) => [image.url, {
    source_url: image.url,
    sha256: image.sha256,
    description: cache.get(image.sha256),
    model: options.model,
    prompt_version: PROMPT_VERSION,
  }]));
  for (const section of relevant) {
    section.imageEvidence = section.imageUrls.map((url) => byUrl.get(url)).filter(Boolean)
      .filter((item, index, items) => items.findIndex((other) => other.sha256 === item.sha256) === index);
  }
  const analyses = unique.map((image) => byUrl.get(image.url));
  return {
    imageCount: urls.length,
    uniqueImages: unique.length,
    analyzed: pending.length,
    reused: unique.length - pending.length,
    analyses,
    imageFailures,
  };
}

function rowsFromSections(sections) {
  const rows = [];
  for (const section of sections) {
    if (!section.targets.length) continue;
    const visual = (section.imageEvidence || []).map((item) => item.description);
    const indicator = section.text || visual.join(" ").slice(0, 700);
    if (!indicator) continue;
    for (const [family, category] of section.targets) {
      const visualDescription = visual.length
        ? ` Gemini visual observations: ${visual.join(" ")}`
        : "";
      const row = {
        family,
        category,
        country: section.country,
        indicator,
        description: `${section.country} ${section.heading} clue normalized from GeoTips.${visualDescription}`,
        source_url: section.sourceUrl,
        source_section: section.heading,
      };
      if (section.imageEvidence?.length) {
        row.image_evidence = section.imageEvidence.map(({ source_url, sha256 }) => ({ source_url, sha256 }));
      }
      rows.push(row);
    }
  }
  return rows;
}

function reportSections(sections) {
  const included = new Map();
  const skipped = new Map();
  for (const section of sections) {
    const target = section.targets.length ? included : skipped;
    target.set(section.heading, (target.get(section.heading) || 0) + 1);
  }
  return {
    included_sections: Object.fromEntries([...included].sort()),
    skipped_sections: Object.fromEntries([...skipped].sort()),
  };
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const definitionPath = path.resolve(options.definition);
  const snapshotPath = path.resolve(options.snapshot);
  const retrievedAt = new Date().toISOString().slice(0, 10);
  const definition = JSON.parse(await readFile(definitionPath, "utf8"));
  const snapshot = JSON.parse(await readFile(snapshotPath, "utf8"));
  let countries = activeCountries(definition);
  if (options.country) {
    countries = countries.filter(({ country, iso2 }) => (
      country.toLowerCase() === options.country.toLowerCase() || iso2.toLowerCase() === options.country.toLowerCase()
    ));
    if (!countries.length) throw new Error(`Country is not active for reference generation: ${options.country}`);
  }

  const pageHtml = new Map();
  const sources = [];
  for (const continent of new Set(countries.map((country) => country.continent))) {
    const url = GEOTIPS_PAGES[continent];
    if (!url) throw new Error(`No GeoTips source configured for ${continent}`);
    const html = await fetchPage(url);
    pageHtml.set(continent, html);
    sources.push({
      name: `GeoTips ${continent}`,
      url,
      retrieved_at: retrievedAt,
      content_sha256: createHash("sha256").update(html).digest("hex"),
    });
  }

  const sections = countries.flatMap(({ country, continent }) => {
    const sourceUrl = GEOTIPS_PAGES[continent];
    return sourceSectionsForCountry(country, pageHtml.get(continent), sourceUrl)
      .map((section) => ({ ...section, country, continent, sourceUrl }));
  });
  const imageStats = await enrichImages(sections, snapshot, options);
  const rows = rowsFromSections(sections).sort((left, right) => left.country.localeCompare(right.country)
    || left.family.localeCompare(right.family) || left.category.localeCompare(right.category)
    || left.source_section.localeCompare(right.source_section));
  const covered = new Set(rows.map((row) => row.country));
  const missing = countries.filter(({ country }) => !covered.has(country));
  if (missing.length) throw new Error(`Missing GeoTips clue coverage: ${missing.map(({ country }) => country).join(", ")}`);

  const report = {
    countries: countries.length,
    rows: rows.length,
    ...imageStats,
    ...reportSections(sections),
  };
  if (options.dryRun) {
    console.log(JSON.stringify(report, null, 2));
    return;
  }

  const refreshedUrls = new Set(sources.map((source) => source.url));
  const preservedSources = snapshot.sources.filter((source) => (
    source.url !== "https://geotips.net/" && !refreshedUrls.has(source.url)
  ));
  const refreshedCountries = new Set(countries.map((country) => country.country));
  const countryNameByIso2 = new Map(definition.countries.map((country) => [country.iso2, country.country]));
  const excludedReferenceCountries = new Set((definition.temporary_exclusions || [])
    .filter((item) => item.scopes?.includes("reference_generation"))
    .map((item) => countryNameByIso2.get(item.iso2)).filter(Boolean));
  const nextSnapshot = {
    ...snapshot,
    retrieved_at: retrievedAt,
    sources: [
      { name: "GeoTips", url: "https://geotips.net/", retrieved_at: retrievedAt },
      ...sources,
      ...preservedSources,
    ],
    rows: [
      ...snapshot.rows.filter((row) => !refreshedCountries.has(row.country)
        && !excludedReferenceCountries.has(row.country)),
      ...rows,
    ].sort((left, right) => String(left.country).localeCompare(String(right.country))
      || String(left.family).localeCompare(String(right.family))
      || String(left.category).localeCompare(String(right.category))),
    enrichment: {
      pipeline: "geotips-section-and-gemini-image-v1",
      image_model: options.analyzeImages ? options.model : null,
      prompt_version: options.analyzeImages ? PROMPT_VERSION : null,
      images_are_transient: true,
      image_analyses: options.analyzeImages ? imageStats.analyses : [],
      image_failures: options.analyzeImages ? imageStats.imageFailures : [],
      excluded_country_iso2: [...new Set((definition.temporary_exclusions || [])
        .filter((item) => item.scopes?.includes("reference_generation"))
        .map((item) => item.iso2))],
      section_report: reportSections(sections),
    },
  };
  await writeFile(snapshotPath, `${JSON.stringify(nextSnapshot, null, 2)}\n`, "utf8");
  console.log(`Wrote ${rows.length} GeoTips rows covering ${covered.size} active countries to ${snapshotPath}`);
  console.log(`Relevant image URLs: ${imageStats.imageCount}; unique hashes: ${imageStats.uniqueImages}; analyzed: ${imageStats.analyzed}; reused: ${imageStats.reused}`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}

export {
  activeCountries,
  countryBlocks,
  extractImageUrls,
  sectionBodies,
  targetsForHeading,
  visibleText,
};
