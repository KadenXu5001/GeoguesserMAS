#!/usr/bin/env node

import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { sectionBodies, visibleText } from "./update_reference_clues.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFINITION = path.join(ROOT, "data", "dataset_definitions", "worldwide_v2.json");
const CAPTURES = path.join(ROOT, "countryhintsfiles");
const OUTPUT = path.join(ROOT, "data", "reference_tables", "countries");

const CATEGORY_ORDER = [
  "driving_side", "license_plates", "road_markings", "language_script", "country_domains",
  "bollards", "chevrons_guardrails", "vehicles", "urban_architecture", "urban_utility_poles",
  "urban_signage", "street_names_addresses", "businesses_domains", "sidewalks_curbs",
  "public_transit", "soil_geology", "vegetation_biomes", "terrain_scenery", "climate",
  "agriculture_land_use", "rural_architecture", "rural_utility_poles", "rural_roadside_features",
];

const FAMILY_BY_CATEGORY = Object.fromEntries(CATEGORY_ORDER.map((category, index) => [
  category,
  index < 8 ? "universal" : index < 15 ? "urban" : "rural",
]));

const SOURCE_URLS = {
  Europe: "https://geotips.net/europe/", Asia: "https://geotips.net/asia/",
  "South America": "https://geotips.net/south-america/", Oceania: "https://geotips.net/oceania/",
  "North America": "https://geotips.net/north-america/", Africa: "https://geotips.net/africa/",
};

const SKIP_HEADINGS = /^(?:disclaimer|country flag|capital city|largest cities(?: by population)?|most helpful|google car|rare google .car.|rare car|follow car|google coverage|camera generation|subdivisions?|regions?|traditional clothing|religion)$/i;
const PROVIDER_TEXT = /\b(?:google|street view|coverage|camera generation|gen(?:eration)?\s*[234]|follow car|roof rack|antenna|blur(?:ry)?|trekker|copyright)\b/i;
const IMAGE_REFERENCE = /\b(?:image|photo|picture|pictured|shown|above|below|examples?)\b/i;

function slug(value) {
  return value.normalize("NFKD").replace(/[^\w\s-]/g, "").trim().toLowerCase().replace(/[\s_]+/g, "-");
}

function repairEncoding(value) {
  value = value
    .replaceAll("â€™", "’").replaceAll("â€˜", "‘").replaceAll("â€œ", "“").replaceAll("â€", "”")
    .replaceAll("â€“", "–").replaceAll("â€”", "—").replaceAll("â€¦", "…")
    .replaceAll("Ã¢", "â").replaceAll("Ãª", "ê").replaceAll("Ã»", "û");
  if (!/[Ãâ]/.test(value)) return value;
  const cp1252 = new Map([
    [0x20ac, 0x80], [0x201a, 0x82], [0x0192, 0x83], [0x201e, 0x84], [0x2026, 0x85],
    [0x2020, 0x86], [0x2021, 0x87], [0x02c6, 0x88], [0x2030, 0x89], [0x0160, 0x8a],
    [0x2039, 0x8b], [0x0152, 0x8c], [0x017d, 0x8e], [0x2018, 0x91], [0x2019, 0x92],
    [0x201c, 0x93], [0x201d, 0x94], [0x2022, 0x95], [0x2013, 0x96], [0x2014, 0x97],
    [0x02dc, 0x98], [0x2122, 0x99], [0x0161, 0x9a], [0x203a, 0x9b], [0x0153, 0x9c],
    [0x017e, 0x9e], [0x0178, 0x9f],
  ]);
  const bytes = [];
  for (const character of value) {
    const code = character.codePointAt(0);
    if (code <= 0xff) bytes.push(code);
    else if (cp1252.has(code)) bytes.push(cp1252.get(code));
    else return value;
  }
  const repaired = Buffer.from(bytes).toString("utf8");
  return repaired.includes("�") ? value : repaired;
}

function normalizedText(body) {
  return repairEncoding(visibleText(body)).replace(/\s+/g, " ").replace(/^\s*[.;:-]+\s*/, "").trim();
}

function sentences(text) {
  return (text.match(/[^.!?]+(?:[.!?]+|$)/g) || []).map((item) => item.trim())
    .filter((item) => /[\p{L}\p{N}]{2}/u.test(item));
}

function usefulSentences(text) {
  return sentences(text)
    .filter((item) => !PROVIDER_TEXT.test(item))
    .filter((item) => !/^(?:note|notice|remember|keep in mind|click|credit)\b/i.test(item))
    .filter((item) => !IMAGE_REFERENCE.test(item));
}

function categoryFor(heading, text) {
  const value = `${heading} ${text}`;
  if (/driving side/i.test(heading)) return "driving_side";
  if (/license plates?/i.test(heading)) return "license_plates";
  if (/road (?:lines?|markings?|layout)/i.test(heading)) {
    if (/curbs?|kerbs?/i.test(text) && !/(?:divider|center|centre|shoulder|line)/i.test(text)) return "sidewalks_curbs";
    return "road_markings";
  }
  if (/(?:alphabet|script|language)/i.test(heading)) return "language_script";
  if (/domain/i.test(heading)) return "country_domains";
  if (/bollards?/i.test(heading)) return /kilomet(?:er|re)|\bkm\b|road marker/i.test(text)
    ? "rural_roadside_features" : "bollards";
  if (/unique vehicles?|rare vehicles?/i.test(heading)) return /taxi|bus|tram|public/i.test(text) ? "public_transit" : "vehicles";
  if (/street signs?|town names?|addresses?/i.test(heading)) return "street_names_addresses";
  if (/road signs?|highway signs?|road numbering|guide to understanding signs|highways?/i.test(heading)) {
    if (/chevron|guardrail|sign backs?/i.test(text)) return "chevrons_guardrails";
    return /route|highway|road number|kilomet(?:er|re)|\bkm\b/i.test(value) ? "rural_roadside_features" : "urban_signage";
  }
  if (/electricity poles?|utility poles?/i.test(heading)) return /street ?lights?|urban|city/i.test(text)
    ? "urban_utility_poles" : "rural_utility_poles";
  if (/architecture|buildings?|houses?/i.test(heading)) return /rural|village|farm|countryside/i.test(text)
    ? "rural_architecture" : "urban_architecture";
  if (/phone|currency|business|companies|ads/i.test(heading)) return "businesses_domains";
  if (/vegetation|specific (?:plants?|trees?)|regional plants?/i.test(heading)) return "vegetation_biomes";
  if (/topography|general look|terrain|scenery/i.test(heading)) return "terrain_scenery";
  if (/climate|weather/i.test(heading)) return "climate";
  if (/agriculture|crops?|farms?|land use/i.test(heading)) return "agriculture_land_use";
  if (/soil|geology/i.test(heading)) return "soil_geology";
  return null;
}

function splitClues(heading, text) {
  const usable = usefulSentences(text);
  if (!usable.length) return [];
  const chunks = [];
  let current = [];
  let length = 0;
  let currentCategory = null;
  for (const sentence of usable) {
    const sentenceCategory = categoryFor(heading, sentence);
    const boundary = /^(?:the |in |around |near |northern|southern|eastern|western|central|far |specific |another |also |additionally)/i.test(sentence);
    if (current.length && (sentenceCategory !== currentCategory || length + sentence.length > 650 || (boundary && length > 260))) {
      chunks.push(current.join(" "));
      current = [];
      length = 0;
    }
    current.push(sentence);
    length += sentence.length + 1;
    currentCategory = sentenceCategory;
  }
  if (current.length) chunks.push(current.join(" "));
  return chunks;
}

function colorPhrase(text) {
  const colors = [...new Set((text.match(/\b(?:black|white|yellow|red|blue|green|orange|gray|grey|silver)\b/gi) || [])
    .map((item) => item.toLowerCase().replace("grey", "gray")))];
  return colors.slice(0, 3).join(" and ");
}

function indicatorFor(category, description, index) {
  const colors = colorPhrase(description);
  const fixed = {
    driving_side: "Driving side", license_plates: `${colors ? `${colors} ` : "Distinctive "}license plates`,
    road_markings: `${colors ? `${colors} ` : "Distinctive "}road markings`,
    language_script: "Language and script", country_domains: "Country internet domain",
    bollards: `${colors ? `${colors} ` : "Distinctive "}bollards`, chevrons_guardrails: "Chevrons and guardrails",
    vehicles: "Distinctive vehicles", urban_architecture: "Urban architectural traits",
    urban_utility_poles: "Urban utility-pole traits", urban_signage: "Urban sign conventions",
    street_names_addresses: "Street-name and address conventions", businesses_domains: "Business and number conventions",
    sidewalks_curbs: `${colors ? `${colors} ` : "Distinctive "}curbs and sidewalks`, public_transit: "Distinctive public transit",
    soil_geology: "Soil and geology", vegetation_biomes: "Vegetation and biome traits",
    terrain_scenery: "Terrain and scenery", climate: "Climate pattern", agriculture_land_use: "Agriculture and land use",
    rural_architecture: "Rural architectural traits", rural_utility_poles: "Rural utility-pole traits",
    rural_roadside_features: "Rural roadside conventions",
  }[category];
  if (index === 0) return fixed;
  const prefix = description.replace(/^[^\p{L}\p{N}]+/u, "").split(/[,;:.]/)[0]
    .replace(/^(?:in|the|a|an|there (?:is|are)|you (?:can|will) (?:see|find)|\w+ (?:uses?|has|features?))\s+/i, "")
    .trim();
  return (prefix.length >= 8 ? prefix : `${fixed} variant ${index + 1}`).slice(0, 80);
}

function rowsForCountry(country, sourceUrl, sections) {
  const rows = [];
  const skipped = [];
  const included = [];
  let hasRelevantImages = false;
  for (const section of sections) {
    const heading = repairEncoding(section.heading);
    const text = normalizedText(section.body);
    const imageBearing = /<img\b/i.test(section.body);
    const sectionCategory = SKIP_HEADINGS.test(heading) ? null : categoryFor(heading, text);
    const clues = sectionCategory ? splitClues(heading, text) : [];
    if (imageBearing && sectionCategory) hasRelevantImages = true;
    if (!clues.length) {
      const reason = SKIP_HEADINGS.test(heading) ? "Excluded or provider-specific section."
        : !/[\p{L}\p{N}]{2}/u.test(text) ? "No explicit textual clue."
          : !sectionCategory ? "No reliable allowed-category mapping." : "Only prohibited, duplicative, or image-dependent text remained.";
      skipped.push({ section: heading, reason });
      continue;
    }
    included.push(heading);
    for (const [index, description] of clues.entries()) {
      const category = categoryFor(heading, description);
      if (!category) continue;
      rows.push({
        family: FAMILY_BY_CATEGORY[category], category, country: country.country,
        indicator: indicatorFor(category, description, index), description,
        source_url: sourceUrl, source_section: heading,
      });
    }
  }
  const deduplicated = rows.filter((row, index, items) => items.findIndex((item) => (
    item.category === row.category && item.description.toLowerCase() === row.description.toLowerCase()
  )) === index);
  const indicatorCounts = new Map();
  for (const row of deduplicated) {
    const base = row.indicator;
    const key = `${row.category}\0${base.toLowerCase()}`;
    const count = indicatorCounts.get(key) || 0;
    indicatorCounts.set(key, count + 1);
    if (count) row.indicator = `${base} — ${row.source_section}${count > 1 ? ` ${count + 1}` : ""}`;
  }
  deduplicated.sort((left, right) => CATEGORY_ORDER.indexOf(left.category) - CATEGORY_ORDER.indexOf(right.category)
    || left.indicator.localeCompare(right.indicator, "en", { sensitivity: "base" }));
  const uniqueIncluded = [...new Set(included)];
  return {
    country: country.country,
    source_url: sourceUrl,
    rows: deduplicated,
    audit: {
      included_sections: uniqueIncluded,
      skipped_sections: skipped.filter((item, index, items) => items.findIndex((other) => other.section === item.section) === index),
      section_count: uniqueIncluded.length,
      row_count: deduplicated.length,
      warnings: hasRelevantImages
        ? ["Local deterministic extraction used GeoTips text only; associated images were not interpreted, so descriptions contain no image-derived details."]
        : [],
    },
  };
}

function validate(document) {
  const problems = [];
  const seen = new Set();
  for (const [index, row] of document.rows.entries()) {
    if (FAMILY_BY_CATEGORY[row.category] !== row.family) problems.push(`row ${index} family/category mismatch`);
    if (row.country !== document.country || row.source_url !== document.source_url) problems.push(`row ${index} provenance mismatch`);
    if (PROVIDER_TEXT.test(`${row.indicator} ${row.description}`)) problems.push(`row ${index} provider metadata`);
    const signature = `${row.category}\0${row.indicator.toLowerCase()}`;
    if (seen.has(signature)) problems.push(`row ${index} duplicate indicator`);
    seen.add(signature);
  }
  if (document.audit.section_count !== new Set(document.audit.included_sections).size) problems.push("section_count mismatch");
  if (document.audit.row_count !== document.rows.length) problems.push("row_count mismatch");
  if (problems.length) throw new Error(`${document.country}: ${problems.join("; ")}`);
}

async function main() {
  const definition = JSON.parse(await readFile(DEFINITION, "utf8"));
  const excluded = new Set((definition.temporary_exclusions || [])
    .filter((item) => item.scopes?.includes("reference_generation")).map((item) => item.iso2));
  const requested = process.argv[2]?.toLowerCase();
  let countries = definition.countries.filter((item) => !excluded.has(item.iso2));
  if (requested) countries = countries.filter((item) => item.country.toLowerCase() === requested || item.iso2.toLowerCase() === requested);
  if (!countries.length) throw new Error(`Unknown or excluded country: ${process.argv[2]}`);
  await mkdir(OUTPUT, { recursive: true });
  for (const country of countries) {
    const html = await readFile(path.join(CAPTURES, `${country.iso2.toLowerCase()}-${slug(country.country)}.html`), "utf8");
    const main = html.split("<main>")[1]?.split("</main>")[0] || html;
    const document = rowsForCountry(country, SOURCE_URLS[country.continent], sectionBodies(main));
    validate(document);
    const filename = `${slug(country.country)}-${country.iso2}.json`;
    await writeFile(path.join(OUTPUT, filename), `${JSON.stringify(document, null, 2)}\n`, "utf8");
    console.log(`${filename}: ${document.audit.row_count} rows`);
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => { console.error(error.message); process.exitCode = 1; });
}

export { CATEGORY_ORDER, FAMILY_BY_CATEGORY, rowsForCountry, validate };
