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
    subparsers.add_parser(
        "download-boundaries", help="download the pinned Natural Earth country boundaries"
    )

    ingest = subparsers.add_parser(
        "ingest-pictures", help="validate, download, and render pilot Mapillary panoramas"
    )
    ingest.add_argument("--limit", type=int, default=1)
    ingest.add_argument("--country", choices=["FR", "TH", "BR"])
    ingest.add_argument("--split", choices=["development", "evaluation"], default="development")

    pictures = subparsers.add_parser(
        "list-pictures", help="list downloaded/rendered panorama metadata"
    )
    pictures.add_argument("--country", choices=["FR", "TH", "BR"])
    pictures.add_argument("--status")

    sheet = subparsers.add_parser(
        "contact-sheet", help="create a four-heading contact sheet for one panorama"
    )
    sheet.add_argument("image_id")
    sheet.add_argument("--output", type=Path)

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
    if args.command == "download-boundaries":
        from geoguesser.boundaries import download_natural_earth

        print(download_natural_earth())
        return 0
    if args.command in {"ingest-pictures", "list-pictures", "contact-sheet"}:
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
                        "panorama_path": item.get("panorama_file", {}).get("path"),
                        "rendered_views": len(item.get("rendered_views", [])),
                    }
                    for item in panoramas
                ]
                print(json.dumps(safe_rows, indent=2))
                return 0
            from geoguesser.picture_pipeline import create_contact_sheet

            panorama = database.panoramas.find_one(
                {"mapillary_image_id": args.image_id}
            )
            if panorama is None:
                raise SystemExit(f"unknown Mapillary image id: {args.image_id}")
            output = args.output or Path(".artifacts/contact-sheets") / f"{args.image_id}.jpg"
            print(create_contact_sheet(panorama, output))
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
