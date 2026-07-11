from __future__ import annotations

import argparse
from pathlib import Path

from geoguesser.cost_model import main as print_cost_model
from geoguesser.panorama import render_cardinal_views


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GeoGuessr Phase 0 utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("cost-model", help="print the current modeled path costs")

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
