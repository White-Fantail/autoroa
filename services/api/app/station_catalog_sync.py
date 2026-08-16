import argparse
import json
import logging

from .station_catalog import run_full_catalog_sync, run_saturated_refinement


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed, refresh, or refine the New Zealand fuel-station catalog.")
    parser.add_argument("--start-cursor", type=int, default=0, help="Catalog cell cursor to resume from (default: 0).")
    parser.add_argument("--max-cells", type=int, default=None, help="Maximum number of catalog cells to process; omit for the full catalog.")
    parser.add_argument("--sleep-seconds", type=float, default=0.05, help="Delay between batches (default: 0.05).")
    parser.add_argument("--refine-saturated", action="store_true", help="Only refine the deepest saturated cells already saved in Postgres; does not rescan all 648 catalog cells.")
    args = parser.parse_args()

    if args.start_cursor < 0: parser.error("--start-cursor must be >= 0")
    if args.max_cells is not None and args.max_cells <= 0: parser.error("--max-cells must be > 0")
    if args.sleep_seconds < 0: parser.error("--sleep-seconds must be >= 0")
    if args.refine_saturated and (args.start_cursor != 0 or args.max_cells is not None): parser.error("--refine-saturated cannot be combined with --start-cursor or --max-cells")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = run_saturated_refinement(sleep_seconds=args.sleep_seconds) if args.refine_saturated else run_full_catalog_sync(start_cursor=args.start_cursor, max_cells=args.max_cells, sleep_seconds=args.sleep_seconds)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
