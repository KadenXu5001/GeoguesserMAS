#!/usr/bin/env node

import { readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BASE_PATH = path.join(ROOT, "data", "reference_tables", "reference_v1.json");
const COUNTRY_DIR = path.join(ROOT, "data", "reference_tables", "countries");
const OUTPUT_PATH = path.join(ROOT, "data", "reference_tables", "reference_v2.json");
const DEFINITION_PATH = path.join(ROOT, "data", "dataset_definitions", "worldwide_v2.json");

const GEOTIPS_REGIONAL_URLS = new Set([
  "https://geotips.net/europe/",
  "https://geotips.net/asia/",
  "https://geotips.net/south-america/",
  "https://geotips.net/oceania/",
  "https://geotips.net/north-america/",
  "https://geotips.net/africa/",
]);

const CATEGORY_ORDER = [
  "driving_side", "license_plates", "road_markings", "language_script", "country_domains",
  "bollards", "chevrons_guardrails", "vehicles", "urban_architecture", "urban_utility_poles",
  "urban_signage", "street_names_addresses", "businesses_domains", "sidewalks_curbs",
  "public_transit", "soil_geology", "vegetation_biomes", "terrain_scenery", "climate",
  "agriculture_land_use", "rural_architecture", "rural_utility_poles", "rural_roadside_features",
];

function rowKey(row) {
  return [row.country || "", row.category, row.indicator, row.source_url].join("\u0000");
}

function assertCountryDocument(document, expectedCountries) {
  if (!expectedCountries.has(document.country)) throw new Error(`Unexpected country file: ${document.country}`);
  if (!Array.isArray(document.rows) || document.audit?.row_count !== document.rows.length) {
    throw new Error(`${document.country}: invalid rows or audit row_count`);
  }
  for (const row of document.rows) {
    if (row.country !== document.country || row.source_url !== document.source_url) {
      throw new Error(`${document.country}: row provenance mismatch`);
    }
    if (!CATEGORY_ORDER.includes(row.category) || !row.indicator || !row.description) {
      throw new Error(`${document.country}: invalid reference row`);
    }
  }
}

async function buildSnapshot() {
  const [base, definition, filenames] = await Promise.all([
    readFile(BASE_PATH, "utf8").then(JSON.parse),
    readFile(DEFINITION_PATH, "utf8").then(JSON.parse),
    readdir(COUNTRY_DIR),
  ]);
  const excluded = new Set((definition.temporary_exclusions || [])
    .filter((item) => item.scopes?.includes("reference_generation"))
    .map((item) => item.iso2));
  const activeCountries = new Set(definition.countries
    .filter((item) => !excluded.has(item.iso2)).map((item) => item.country));
  const countryFiles = filenames.filter((name) => name.endsWith(".json")).sort();
  const documents = [];
  for (const filename of countryFiles) {
    const document = JSON.parse(await readFile(path.join(COUNTRY_DIR, filename), "utf8"));
    assertCountryDocument(document, activeCountries);
    documents.push(document);
  }
  const represented = new Set(documents.map((document) => document.country));
  const missing = [...activeCountries].filter((country) => !represented.has(country));
  if (documents.length !== activeCountries.size || missing.length) {
    throw new Error(`Country handoff mismatch; files=${documents.length}, expected=${activeCountries.size}, missing=${missing.join(", ")}`);
  }

  const preserved = base.rows.filter((row) => activeCountries.has(row.country)
    && !GEOTIPS_REGIONAL_URLS.has(row.source_url));
  const localRows = documents.flatMap((document) => document.rows);
  const rowsByKey = new Map();
  for (const row of [...preserved, ...localRows]) rowsByKey.set(rowKey(row), row);
  const rows = [...rowsByKey.values()].sort((left, right) => (
    left.country.localeCompare(right.country)
    || CATEGORY_ORDER.indexOf(left.category) - CATEGORY_ORDER.indexOf(right.category)
    || left.indicator.localeCompare(right.indicator, "en", { sensitivity: "base" })
  ));
  const usedSourceUrls = new Set(rows.map((row) => row.source_url));
  const sources = base.sources.filter((source) => (
    source.url === "https://geotips.net/" || usedSourceUrls.has(source.url)
  ));

  return {
    ...base,
    version: "reference-v2",
    retrieved_at: "2026-07-20",
    sources,
    rows,
    enrichment: {
      pipeline: "local-geotips-country-files-v2",
      base_version: base.version,
      country_file_count: documents.length,
      preserved_non_geotips_rows: preserved.length,
      local_geotips_rows: localRows.length,
      merged_row_count: rows.length,
      images_are_transient: true,
      image_analyses: [],
      country_audits: Object.fromEntries(documents.map((document) => [document.country, document.audit])),
    },
  };
}

async function main() {
  const snapshot = await buildSnapshot();
  await writeFile(OUTPUT_PATH, `${JSON.stringify(snapshot, null, 2)}\n`, "utf8");
  console.log(`Wrote ${snapshot.rows.length} rows to ${path.relative(ROOT, OUTPUT_PATH)}`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => { console.error(error.message); process.exitCode = 1; });
}

export { buildSnapshot, rowKey };
