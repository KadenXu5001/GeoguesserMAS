import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import { CATEGORY_ORDER, FAMILY_BY_CATEGORY } from "../../scripts/generate_country_reference_files.mjs";
import { buildSnapshot } from "../../scripts/build_reference_snapshot.mjs";

const ROOT = path.resolve(import.meta.dirname, "../..");
const DIRECTORY = path.join(ROOT, "data", "reference_tables", "countries");

test("local country reference handoff covers every active country with valid ordered JSON", async () => {
  const definition = JSON.parse(await readFile(path.join(ROOT, "data", "dataset_definitions", "worldwide_v2.json"), "utf8"));
  const excluded = new Set(definition.temporary_exclusions
    .filter((item) => item.scopes.includes("reference_generation")).map((item) => item.iso2));
  const expected = definition.countries.filter((item) => !excluded.has(item.iso2));
  const files = (await readdir(DIRECTORY)).filter((item) => item.endsWith(".json")).sort();

  assert.equal(files.length, expected.length);
  for (const country of expected) {
    const slug = country.country.toLowerCase().replaceAll(" ", "-");
    const filename = `${slug}-${country.iso2}.json`;
    assert.ok(files.includes(filename), filename);
    const document = JSON.parse(await readFile(path.join(DIRECTORY, filename), "utf8"));
    assert.equal(document.country, country.country);
    assert.equal(document.audit.row_count, document.rows.length);
    assert.equal(document.audit.section_count, new Set(document.audit.included_sections).size);
    assert.deepEqual(Object.keys(document).sort(), ["audit", "country", "rows", "source_url"]);
    let priorCategory = -1;
    let priorIndicator = "";
    for (const row of document.rows) {
      assert.deepEqual(Object.keys(row).sort(), [
        "category", "country", "description", "family", "indicator", "source_section", "source_url",
      ]);
      assert.equal(row.family, FAMILY_BY_CATEGORY[row.category]);
      assert.equal(row.country, country.country);
      assert.equal(row.source_url, document.source_url);
      assert.ok(row.indicator && row.description && row.source_section);
      assert.doesNotMatch(`${row.indicator} ${row.description}`, /\b(?:google|street view|camera generation|follow car|roof rack|antenna)\b/i);
      const category = CATEGORY_ORDER.indexOf(row.category);
      assert.ok(category >= priorCategory);
      if (category === priorCategory) {
        assert.ok(priorIndicator.localeCompare(row.indicator, "en", { sensitivity: "base" }) <= 0);
      }
      priorCategory = category;
      priorIndicator = row.indicator;
    }
  }
});

test("country generator is local-only", async () => {
  const source = await readFile(path.join(ROOT, "scripts", "generate_country_reference_files.mjs"), "utf8");
  assert.doesNotMatch(source, /\bfetch\s*\(|generativelanguage|GEMINI_API_KEY|GOOGLE_API_KEY/);
});

test("reference-v2 is reproducible and exposes every selected utility-pole row", async () => {
  const generated = await buildSnapshot();
  const stored = JSON.parse(await readFile(
    path.join(ROOT, "data", "reference_tables", "reference_v2.json"), "utf8",
  ));

  assert.deepEqual(stored, generated);
  assert.equal(stored.version, "reference-v2");
  assert.equal(stored.enrichment.country_file_count, 29);
  assert.equal(stored.enrichment.local_geotips_rows, 402);
  assert.equal(stored.rows.filter((row) => row.category === "urban_utility_poles").length, 9);
  assert.equal(stored.rows.filter((row) => row.category === "rural_utility_poles").length, 23);
  assert.ok(stored.rows.every((row) => !("image_evidence" in row)));
});
