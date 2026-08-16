import argparse
import json

from app.station_catalog import run_full_catalog_sync


def main():
    parser = argparse.ArgumentParser(description="Seed/refresh the New Zealand fuel-station catalog from Google Places.")
    parser.add_argument("--start-cursor", type=int, default=0, help="Resume from this catalog cell cursor.")
    parser.add_argument("--max-cells", type=int, default=None, help="Optional maximum number of cells to process.")
    parser.add_argument("--sleep-seconds", type=float, default=0.05, help="Pause between 10-cell DB batches.")
    args = parser.parse_args()
    result = run_full_catalog_sync(
        start_cursor=args.start_cursor,
        max_cells=args.max_cells,
        sleep_seconds=args.sleep_seconds,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
