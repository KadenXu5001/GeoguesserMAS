# Country-by-country GeoTips enrichment prompt

Copy the prompt below into a new ChatGPT conversation. Replace `COUNTRY_NAME` and
`GEOTIPS_CONTINENT_URL` before submitting it.

Morocco is temporarily excluded from play, reference generation, and evaluation, so skip Morocco
until that hold is intentionally removed. Tunisia already has a completed pilot enrichment in the
current reference snapshot.

## Prompt

```text
I am building a deterministic GeoGuessr clue database for COUNTRY_NAME.

Source:
GEOTIPS_CONTINENT_URL

Find COUNTRY_NAME on that GeoTips page and inspect every section and every accessible image
belonging to that country.

Goal:
Return normalized, source-backed clues for COUNTRY_NAME using only the categories listed below.

Allowed categories

Universal:
- driving_side
- license_plates
- road_markings
- language_script
- country_domains
- bollards
- chevrons_guardrails
- vehicles

Urban:
- urban_architecture
- urban_utility_poles
- urban_signage
- street_names_addresses
- businesses_domains
- sidewalks_curbs
- public_transit

Rural:
- soil_geology
- vegetation_biomes
- terrain_scenery
- climate
- agriculture_land_use
- rural_architecture
- rural_utility_poles
- rural_roadside_features

Rules:

1. Read every clue-bearing section for COUNTRY_NAME.
2. Open and visually inspect every accessible image in those sections.
3. Paraphrase the source. Do not copy long passages verbatim.
4. Record only visible or explicitly stated clues. Do not invent missing information.
5. Exclude:
   - country flags
   - capital-city trivia
   - subdivisions or region lists
   - Google car metadata
   - camera generations
   - Google Street View coverage
   - coverage-specific blur, antennas, roof racks, or capture artifacts
6. Do not identify image contents using assumed knowledge of the country. Describe what is actually
   visible.
7. If an image is unavailable, record its URL in `inaccessible_images`.
8. Sections may map to multiple categories when genuinely useful to different specialists. For
   example:
   - Architecture -> urban_architecture and/or rural_architecture
   - Electricity poles -> urban_utility_poles and/or rural_utility_poles
   - Road signs -> urban_signage and/or rural_roadside_features
   - Vegetation/Landscape -> vegetation_biomes and/or terrain_scenery
   - Unique public vehicles/taxis -> vehicles and/or public_transit
9. Keep each indicator concise but specific.
10. Include all distinct useful image observations in the description.
11. Do not recommend a vector database or change the schema.
12. Return valid JSON only, without Markdown fences or commentary.

Output schema:

{
  "country": "COUNTRY_NAME",
  "source_url": "GEOTIPS_CONTINENT_URL",
  "rows": [
    {
      "family": "universal | urban | rural",
      "category": "one allowed category",
      "country": "COUNTRY_NAME",
      "indicator": "Concise clue suitable for deterministic lookup",
      "description": "Paraphrased textual evidence plus distinct visual observations.",
      "source_url": "GEOTIPS_CONTINENT_URL",
      "source_section": "Exact GeoTips section heading",
      "image_evidence": [
        {
          "source_url": "DIRECT_IMAGE_URL",
          "description": "Concise description of the visible clue"
        }
      ]
    }
  ],
  "audit": {
    "included_sections": ["section names"],
    "skipped_sections": [
      {
        "section": "section name",
        "reason": "Why it was excluded or could not map reliably"
      }
    ],
    "inaccessible_images": ["DIRECT_IMAGE_URL"],
    "warnings": ["Any ambiguity or source-quality concerns"]
  }
}

Before returning JSON, verify:
- every family/category combination is allowed;
- every row has an indicator, description, source URL, and source section;
- provider-specific Google metadata is absent;
- every useful accessible image was inspected;
- uncertain observations are worded cautiously.
```

## GeoTips continent URLs

- Europe: `https://geotips.net/europe/`
- Asia: `https://geotips.net/asia/`
- South America: `https://geotips.net/south-america/`
- Oceania: `https://geotips.net/oceania/`
- North America: `https://geotips.net/north-america/`
- Africa: `https://geotips.net/africa/`

## Handoff

Save each response as valid UTF-8 JSON, ideally named with the ISO country code, such as
`tunisia-TN.json`. Return the JSON file for validation and merging into
`data/reference_tables/reference_v1.json`.
