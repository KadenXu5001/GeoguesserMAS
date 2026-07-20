import assert from "node:assert/strict";
import test from "node:test";

import {
  activeCountries,
  extractImageUrls,
  targetsForHeading,
  visibleText,
} from "../../scripts/update_reference_clues.mjs";
import {
  completeHtml,
  imageResources,
  normalizeImageTags,
  slug,
} from "../../scripts/download_country_hint_files.mjs";

test("reference exclusions are scoped without changing the frozen taxonomy", () => {
  const definition = {
    countries: [
      { iso2: "MA", country: "Morocco" },
      { iso2: "TN", country: "Tunisia" },
    ],
    temporary_exclusions: [{ iso2: "MA", scopes: ["reference_generation"] }],
  };

  assert.deepEqual(activeCountries(definition).map((item) => item.iso2), ["TN"]);
  assert.equal(definition.countries.length, 2);
});

test("GeoTips headings map only into existing specialist categories", () => {
  assert.deepEqual(targetsForHeading("Road Lines"), [["universal", "road_markings"]]);
  assert.deepEqual(targetsForHeading("Architecture"), [
    ["urban", "urban_architecture"],
    ["rural", "rural_architecture"],
  ]);
  assert.deepEqual(targetsForHeading("Regional Plants"), [
    ["rural", "vegetation_biomes"],
    ["rural", "terrain_scenery"],
  ]);
  assert.deepEqual(targetsForHeading("Google Car"), []);
  assert.deepEqual(targetsForHeading("Country Flag"), []);
});

test("image extraction prefers full linked assets and normalizes visible text", () => {
  const html = '<a href="/uploads/full.jpg"><img src="/uploads/thumb-300x200.jpg"></a><p>White &amp; red.</p>';
  assert.deepEqual(extractImageUrls(html, "https://geotips.net/africa/"), [
    "https://geotips.net/uploads/full.jpg",
  ]);
  assert.equal(visibleText(html), "White & red.");
});

test("country file helpers preserve page content and discover image assets", () => {
  const section = '<p>Road clue</p><img src="/media/clue.jpg"><a href="/media/full.png">Full</a>';
  assert.deepEqual(imageResources(section, "https://geotips.net/europe/"), [
    { attributeValue: "/media/clue.jpg", url: "https://geotips.net/media/clue.jpg" },
    { attributeValue: "/media/full.png", url: "https://geotips.net/media/full.png" },
  ]);
  assert.match(completeHtml({
    country: "New Zealand",
    continent: "Oceania",
    sourceUrl: "https://geotips.net/oceania/",
    retrievedAt: "2026-07-20T00:00:00Z",
    countryHtml: section,
  }), /Road clue/);
  assert.equal(slug("New Zealand"), "new-zealand");
});

test("country files replace lazy placeholders with the real image source", () => {
  const markup = '<img src="data:image/gif;base64,placeholder" data-src="data:image/png;base64,actual" srcset="ignored">';

  assert.equal(
    normalizeImageTags(markup),
    '<img src="data:image/png;base64,actual">',
  );
});
