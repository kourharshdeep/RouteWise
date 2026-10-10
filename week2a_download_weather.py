"""
Week 2A: Download ERA5-Land weather for the NH-44 pilot corridor
-----------------------------------------------------------------
Variables: total precipitation, snowfall, 2 m temperature, snow depth.
One request per year (a single 5-year request is rejected by CDS as too large).

Before the FIRST run:
  1. Your key must be in C:\\Users\\<you>\\.cdsapirc  (already done).
  2. Open https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land
     -> "Download" tab -> scroll to the bottom -> accept the Terms of use.
     Without this, every request fails with a "licence not accepted" error.

Run a quick test first (1 month only, a few minutes):
    python week2a_download_weather.py --test
Then the full download:
    python week2a_download_weather.py
"""
import argparse
import os
import zipfile

import cdsapi

# Same corridor as Week 1
NORTH, SOUTH, EAST, WEST = 33.475, 33.211, 75.262, 75.161
PAD = 0.15  # ERA5-Land grid is 0.1 degrees, so pad to be sure we cover the box
AREA = [
    round(NORTH + PAD, 2),
    round(WEST - PAD, 2),
    round(SOUTH - PAD, 2),
    round(EAST + PAD, 2),
]  # CDS order: North, West, South, East

OUT_DIR = "data/weather"
VARIABLES = ["total_precipitation", "snowfall", "2m_temperature", "snow_depth"]
# 4 readings a day is enough. The 00:00 value of accumulated variables
# (precipitation, snowfall) holds the PREVIOUS day's total; week2b handles this.
TIMES = ["00:00", "06:00", "12:00", "18:00"]


def download(year, months, target, client):
    request = {
        "variable": VARIABLES,
        "year": str(year),
        "month": months,
        "day": [f"{d:02d}" for d in range(1, 32)],
        "time": TIMES,
        "area": AREA,
        "data_format": "netcdf",
        "download_format": "unarchived",
    }
    print(f"Requesting {year} ({len(months)} month(s)) -> {target}")
    client.retrieve("reanalysis-era5-land", request, target)

    # CDS sometimes returns a zip with several .nc files inside. Unpack if so.
    if zipfile.is_zipfile(target):
        zpath = target + ".zip"
        os.replace(target, zpath)
        folder = target[:-3]
        with zipfile.ZipFile(zpath) as z:
            z.extractall(folder)
        os.remove(zpath)
        print(f"  unpacked zip into {folder}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="download one month only")
    parser.add_argument("--start", type=int, default=2021)
    parser.add_argument("--end", type=int, default=2025)
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    client = cdsapi.Client()

    if args.test:
        jobs = [(2024, ["07"], f"{OUT_DIR}/era5land_test.nc")]
    else:
        all_months = [f"{m:02d}" for m in range(1, 13)]
        jobs = [
            (y, all_months, f"{OUT_DIR}/era5land_{y}.nc")
            for y in range(args.start, args.end + 1)
        ]

    for year, months, target in jobs:
        folder = target[:-3]
        if os.path.exists(target) or os.path.isdir(folder):
            print(f"Skipping {year}: already downloaded")
            continue
        download(year, months, target, client)

    print("Done. Files are in", OUT_DIR)


if __name__ == "__main__":
    main()