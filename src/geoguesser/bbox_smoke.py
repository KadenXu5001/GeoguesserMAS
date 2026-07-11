from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image, ImageDraw

from geoguesser.bbox import crop_normalized_bbox, normalize_bbox_1000
from geoguesser.panorama import render_perspective


PROMPT = """Detect up to 8 prominent, geographically useful objects in this street scene.
Return only a JSON array. Each item must have:
- box_2d: [ymin, xmin, ymax, xmax] integer coordinates normalized 0-1000
- label: a short descriptive label
Include visible signs, vehicles, road markings, bollards, utility poles, or distinctive buildings.
Return [] if none are visible."""


def fetch_pano(image_id: str, token: str, output: Path) -> bool:
    metadata = requests.get(
        f"https://graph.mapillary.com/{image_id}",
        params={
            "access_token": token,
            "fields": "id,is_pano,thumb_original_url",
        },
        timeout=30,
    )
    metadata.raise_for_status()
    payload = metadata.json()
    if not payload.get("is_pano") or not payload.get("thumb_original_url"):
        return False
    image_response = requests.get(payload["thumb_original_url"], timeout=60)
    image_response.raise_for_status()
    output.write_bytes(image_response.content)
    return True


def detect_objects(client: genai.Client, model: str, image: Image.Image) -> list[dict]:
    response = client.models.generate_content(
        model=model,
        contents=[image, PROMPT],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            max_output_tokens=1200,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
    start_candidates = [index for index in (text.find("["), text.find("{")) if index >= 0]
    if not start_candidates:
        raise ValueError("object detection response contained no JSON value")
    parsed, _ = json.JSONDecoder().raw_decode(text[min(start_candidates) :])
    if isinstance(parsed, dict):
        parsed = parsed.get("objects", parsed.get("boxes", []))
    if not isinstance(parsed, list):
        raise ValueError("object detection response was not a list")
    return parsed


def annotate(image: Image.Image, objects: list[dict]) -> Image.Image:
    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)
    for item in objects:
        box = item.get("box_2d")
        if not isinstance(box, list) or len(box) != 4:
            continue
        pixel_box = normalize_bbox_1000(box, image.width, image.height)
        draw.rectangle(pixel_box, outline="red", width=4)
        draw.text((pixel_box[0] + 4, pixel_box[1] + 4), str(item.get("label", "object")), fill="red")
    return annotated


def run_smoke_test(
    coverage_path: Path,
    output_dir: Path,
    *,
    count: int,
    model: str,
) -> dict:
    load_dotenv()
    mapillary_token = os.environ["MAPILLARY_ACCESS_TOKEN"]
    gemini_key = os.environ["GEMINI_API_KEY"]
    output_dir.mkdir(parents=True, exist_ok=True)
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    client = genai.Client(api_key=gemini_key)
    results = []

    for country in coverage["countries"]:
        if not country["qualified"] or not country["evidence"]:
            continue
        image_id = country["evidence"][0]["image_id"]
        panorama_path = output_dir / f"{country['iso2']}_{image_id}_pano.jpg"
        if not fetch_pano(image_id, mapillary_token, panorama_path):
            continue
        with Image.open(panorama_path) as panorama:
            view = render_perspective(panorama, 0, size=1024)
        view_path = output_dir / f"{country['iso2']}_{image_id}_h000.jpg"
        view.save(view_path, quality=92)
        objects = detect_objects(client, model, view)
        annotated_path = output_dir / f"{country['iso2']}_{image_id}_annotated.jpg"
        annotate(view, objects).save(annotated_path, quality=92)

        crops = []
        for index, item in enumerate(objects[:5]):
            box = item.get("box_2d")
            if not isinstance(box, list) or len(box) != 4:
                continue
            crop = crop_normalized_bbox(view, box, padding_fraction=0.25)
            crop_path = output_dir / f"{country['iso2']}_{image_id}_crop{index}.jpg"
            crop.save(crop_path, quality=92)
            crops.append(str(crop_path))
        results.append(
            {
                "country": country["country"],
                "image_id": image_id,
                "view": str(view_path),
                "annotated": str(annotated_path),
                "objects": objects,
                "crops": crops,
            }
        )
        if len(results) >= count:
            break

    manifest = {
        "model": model,
        "bbox_convention": "[ymin, xmin, ymax, xmax] normalized 0-1000",
        "padding_fraction": 0.25,
        "results": results,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Gemini bounding boxes on Mapillary panoramas")
    parser.add_argument("--coverage", type=Path, default=Path("data/coverage_scan.json"))
    parser.add_argument("--output", type=Path, default=Path(".artifacts/bbox-smoke"))
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--model", default="gemini-3-flash-preview")
    args = parser.parse_args()
    manifest = run_smoke_test(
        args.coverage,
        args.output,
        count=args.count,
        model=args.model,
    )
    print(f"validated={len(manifest['results'])} model={manifest['model']}")
    return 0 if len(manifest["results"]) >= args.count else 2


if __name__ == "__main__":
    raise SystemExit(main())
