import argparse
import json
import logging

from .station_catalog import run_full_catalog_sync


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed or refresh the New Zealand fuel-station catalog."
    )
    parser.add_argument(
        "--start-cursor",
        type=int,
        default=0,
        help="Catalog cell cursor to resume from (default: 0).",
    )
    parser.add_argument(
        "--max-cells",
        type=int,
        default=None,
        help="Maximum number of catalog cells to process; omit for the full catalog.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.05,
        help="Delay between 10-cell batches (default: 0.05).",
    )
    args = parser.parse_args()

    if args.start_cursor < 0:
        parser.error("--start-cursor must be >= 0")
    if args.max_cells is not None and args.max_cells <= 0:
        parser.error("--max-cells must be > 0")
    if args.sleep_seconds < 0:
        parser.error("--sleep-seconds must be >= 0")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = run_full_catalog_sync(
        start_cursor=args.start_cursor,
        max_cells=args.max_cells,
        sleep_seconds=args.sleep_seconds,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
