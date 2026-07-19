import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import shapefile from "shapefile";
import simplify from "@turf/simplify";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..", "..");
const BOUNDARY_ROOT = path.join(
  ROOT,
  "data",
  "boundaries",
  "natural-earth-5.1.1",
  "ne_10m_admin_0_countries",
);
const OUTPUT = path.join(ROOT, "web", "public", "countries.geojson");

const source = await shapefile.open(`${BOUNDARY_ROOT}.shp`, `${BOUNDARY_ROOT}.dbf`, {
  encoding: "utf-8",
});
const features = [];
const cleanText = (value) => String(value || "").replaceAll("\0", "").trim();

while (true) {
  const item = await source.read();
  if (item.done) break;
  const properties = item.value.properties;
  const iso2 = cleanText(properties.ISO_A2_EH || properties.ISO_A2);
  if (!iso2 || iso2 === "-99") continue;
  const feature = simplify(
    {
      type: "Feature",
      properties: {
        iso2,
        name: cleanText(properties.NAME_EN || properties.ADMIN || properties.NAME),
      },
      geometry: item.value.geometry,
    },
    { tolerance: 0.04, highQuality: false, mutate: false },
  );
  features.push(feature);
}

features.sort((left, right) => left.properties.name.localeCompare(right.properties.name));
await mkdir(path.dirname(OUTPUT), { recursive: true });
await writeFile(
  OUTPUT,
  JSON.stringify({ type: "FeatureCollection", features }),
  "utf-8",
);
console.log(`Wrote ${features.length} country features to ${OUTPUT}`);
