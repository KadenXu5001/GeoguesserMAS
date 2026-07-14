from __future__ import annotations

import argparse
import json
from pathlib import Path

from geoguesser.cost_model import main as print_cost_model
from geoguesser.panorama import render_cardinal_views


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GeoGuessr Phase 0 utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("cost-model", help="print the current modeled path costs")
    subparsers.add_parser(
        "init-mongodb", help="initialize local MongoDB collections, validators, and indexes"
    )
    seed = subparsers.add_parser(
        "seed-references", help="seed the frozen local reference snapshot into MongoDB"
    )
    seed.add_argument(
        "--snapshot", type=Path, default=Path("data/reference_tables/reference_v1.json")
    )
    subparsers.add_parser(
        "download-boundaries", help="download the pinned Natural Earth country boundaries"
    )

    ingest = subparsers.add_parser(
        "ingest-pictures", help="validate, download, and render pilot Mapillary panoramas"
    )
    ingest.add_argument("--limit", type=int, default=1)
    ingest.add_argument("--country", choices=["FR", "TH", "BR"])
    ingest.add_argument("--split", choices=["development", "evaluation"], default="development")
    ingest.add_argument("--coverage-path", type=Path, default=Path("data/coverage_scan.json"))

    pictures = subparsers.add_parser(
        "list-pictures", help="list downloaded/rendered panorama metadata"
    )
    pictures.add_argument("--country", choices=["FR", "TH", "BR"])
    pictures.add_argument("--status")

    manifests = subparsers.add_parser(
        "export-pilot-manifests", help="write dev_v1.csv and eval_c1.csv from approved panoramas"
    )
    manifests.add_argument("--output-dir", type=Path, default=Path("data/datasets"))

    sheet = subparsers.add_parser(
        "contact-sheet", help="create a four-heading contact sheet for one panorama"
    )
    sheet.add_argument("image_id")
    sheet.add_argument("--output", type=Path)

    strip = subparsers.add_parser(
        "strip-preview", help="create an ordered horizontal four-heading preview"
    )
    strip.add_argument("image_id")
    strip.add_argument("--output", type=Path)

    assess = subparsers.add_parser(
        "assess-quality", help="measure and store automatic panorama quality metrics"
    )
    assess.add_argument("image_id")

    review = subparsers.add_parser(
        "review-quality", help="approve or reject a panorama after visual review"
    )
    review.add_argument("image_id")
    review.add_argument("decision", choices=["approve", "reject"])
    review.add_argument("--notes", required=True)

    render = subparsers.add_parser(
        "render-panorama",
        help="render four cardinal perspective views from an equirectangular panorama",
    )
    render.add_argument("panorama", type=Path)
    render.add_argument("output_dir", type=Path)
    render.add_argument("--size", type=int, default=1024)
    render.add_argument("--fov", type=float, default=90.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "cost-model":
        print_cost_model()
        return 0
    if args.command == "init-mongodb":
        from dotenv import load_dotenv

        from geoguesser.storage import MongoRepository, connect_database

        load_dotenv()
        client, database = connect_database()
        try:
            client.admin.command("ping")
            MongoRepository(database).initialize()
        finally:
            client.close()
        print(f"initialized MongoDB database: {database.name}")
        return 0
    if args.command == "seed-references":
        from dotenv import load_dotenv

        from geoguesser.reference_data import load_reference_snapshot
        from geoguesser.storage import MongoRepository, connect_database

        load_dotenv()
        client, database = connect_database()
        try:
            client.admin.command("ping")
            repository = MongoRepository(database)
            repository.initialize()
            snapshot = load_reference_snapshot(args.snapshot)
            seeded = repository.seed_reference_snapshot(snapshot)
        finally:
            client.close()
        print(json.dumps({"version": snapshot["version"], "seeded": seeded}, indent=2))
        return 0
    if args.command == "download-boundaries":
        from geoguesser.boundaries import download_natural_earth

        print(download_natural_earth())
        return 0
    if args.command in {
        "ingest-pictures",
        "list-pictures",
        "export-pilot-manifests",
        "contact-sheet",
        "strip-preview",
        "assess-quality",
        "review-quality",
    }:
        from dotenv import load_dotenv

        from geoguesser.storage import MongoRepository, connect_database

        load_dotenv()
        client, database = connect_database()
        try:
            repository = MongoRepository(database)
            repository.initialize()
            if args.command == "ingest-pictures":
                from geoguesser.boundaries import CountryBoundaries
                from geoguesser.mapillary import MapillaryClient
                from geoguesser.picture_pipeline import ingest_picture_candidates

                result = ingest_picture_candidates(
                    repository,
                    MapillaryClient(),
                    CountryBoundaries(),
                    limit=args.limit,
                    country_iso2=args.country,
                    split=args.split,
                    coverage_path=args.coverage_path,
                )
                print(json.dumps(result, indent=2))
                return 0 if result["failed"] == 0 else 2
            if args.command == "list-pictures":
                panoramas = repository.list_panoramas(
                    country_iso2=args.country,
                    status=args.status,
                )
                safe_rows = [
                    {
                        "image_id": item["mapillary_image_id"],
                        "country": item.get("country_iso2"),
                        "split": item.get("split"),
                        "status": item.get("status"),
                        "automatic_quality_pass": item.get("quality", {}).get(
                            "automatic_pass"
                        ),
                        "manual_quality_status": item.get("quality", {})
                        .get("manual_review", {})
                        .get("status"),
                        "panorama_path": item.get("panorama_file", {}).get("path"),
                        "rendered_views": len(item.get("rendered_views", [])),
                        "rejection_reason": item.get("rejection_reason"),
                    }
                    for item in panoramas
                ]
                print(json.dumps(safe_rows, indent=2))
                return 0
            if args.command == "export-pilot-manifests":
                from geoguesser.dataset_manifest import write_pilot_manifests

                outputs = write_pilot_manifests(repository, args.output_dir)
                print(json.dumps({key: path.as_posix() for key, path in outputs.items()}, indent=2))
                return 0
            panorama = database.panoramas.find_one(
                {"mapillary_image_id": args.image_id}
            )
            if panorama is None:
                raise SystemExit(f"unknown Mapillary image id: {args.image_id}")
            if args.command == "contact-sheet":
                from geoguesser.picture_pipeline import create_contact_sheet

                output = args.output or Path(".artifacts/contact-sheets") / f"{args.image_id}.jpg"
                print(create_contact_sheet(panorama, output))
                return 0
            if args.command == "strip-preview":
                from geoguesser.picture_pipeline import create_horizontal_strip

                output = args.output or Path(".artifacts/strip-previews") / f"{args.image_id}.jpg"
                print(create_horizontal_strip(panorama, output))
                return 0
            if args.command == "assess-quality":
                from geoguesser.quality import assess_panorama

                panorama_path = panorama.get("panorama_file", {}).get("path")
                if not panorama_path:
                    raise SystemExit("panorama has no downloaded file")
                assessment = assess_panorama(Path(panorama_path))
                document = assessment.as_document()
                repository.record_quality(args.image_id, document)
                print(json.dumps(document, indent=2))
                return 0 if assessment.automatic_pass else 2
            repository.review_quality(
                args.image_id,
                approved=args.decision == "approve",
                notes=args.notes,
            )
            print(f"{args.image_id}: {args.decision}")
            return 0
        finally:
            client.close()
    if args.command == "render-panorama":
        outputs = render_cardinal_views(
            args.panorama,
            args.output_dir,
            size=args.size,
            field_of_view_degrees=args.fov,
        )
        for output in outputs:
            print(output)
        return 0
    raise AssertionError(f"unhandled command: {args.command}")
