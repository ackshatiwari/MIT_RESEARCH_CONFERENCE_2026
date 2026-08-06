"""
Download supporting datasets for the data-center / AADT causal study.

Pulls, into External_Data/:
  - Prince William County data-center buildings, campuses, and use permits
    (PWC GIS Open Data Portal / ArcGIS Hub)
  - VDOT road-route geometry, for joining AADT segments (Route Label / RTE_NM)
    to real coordinates (Virginia GIS Clearinghouse / VDOT ArcGIS Online)
  - Census ACS 5-year tract data (commute mode/time, population, land area)
    for Loudoun County (FIPS 51107) and Prince William County (FIPS 51153)

Known gap (not fetched here): Loudoun County does not publish a plain
downloadable feature layer for data-center buildings/permits the way PWC
does -- its data-center map and building-permit trackers are Esri Experience
Builder dashboards without a documented public REST endpoint. Options:
  1. Manually export from https://www.loudoun.gov/5990/Data-Center-Standards-Locations
     (interactive map has an "Export"/table view for the visible layer).
  2. Use the "Loudoun Zoning" layer fetched below (rezoning case history) and
     filter for data-center-related case types by hand.
  3. FOIA / request the underlying dataset from Loudoun County GIS.
Do not guess a Loudoun data-center endpoint -- verify one before adding it.

All URLs below were verified live (HTTP 200, ArcGIS FeatureServer JSON) on
2026-07-30. ArcGIS Hub item IDs are stable, but re-verify if a fetch starts
failing -- portals occasionally retire/replace layers.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

try:

    import truststore

    truststore.inject_into_ssl()
except ImportError:
    print("NOTE: 'truststore' not installed -- if you hit SSL certificate "
          "errors below, run `pip install truststore` and re-run this script.")

OUT_DIR = Path("External_Data")

USER_AGENT = "Mozilla/5.0 (research script; ISEF traffic/data-center study)"

# The Census API now rejects all requests without a key (verified 2026-07-30 --
# every acs5 year tested, including ones that used to work anonymously,
# returned an HTML "Missing Key" page with a 200 status instead of JSON).
# Get a free key at https://api.census.gov/data/key_signup.html, copy
# .env.example to .env, and paste it in as CENSUS_API_KEY=...
import os

from dotenv import load_dotenv

load_dotenv()

CENSUS_API_KEY = os.environ.get("CENSUS_API_KEY", "")
if CENSUS_API_KEY in ("", "your_census_api_key_here"):
    CENSUS_API_KEY = ""


def _fetch(url: str, timeout: int = 60, retries: int = 3) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (HTTPError, URLError, ConnectionError, TimeoutError, OSError) as e:
            last_err = e
            if attempt < retries:
                wait = 2 ** attempt
                print(f"    (retry {attempt}/{retries - 1} after {e!r}, waiting {wait}s)")
                time.sleep(wait)
    assert last_err is not None
    raise last_err


def download_arcgis_layer(name: str, feature_server_url: str, out_path: Path,
                           where: str = "1=1") -> None:
    """Page through an ArcGIS FeatureServer/MapServer layer and save as GeoJSON.

    Uses the layer's own /query endpoint (resultOffset paging) rather than the
    Hub 'export' redirect, so it works directly against county/VDOT services.
    """
    all_features = None
    offset = 0
    page_size = 1000
    while True:
        params = urlencode({
            "where": where,
            "outFields": "*",
            "f": "geojson",
            "outSR": 4326,
            "resultOffset": offset,
            "resultRecordCount": page_size,
        })
        query_url = f"{feature_server_url}/query?{params}"
        try:
            raw = _fetch(query_url)
        except (HTTPError, URLError, OSError) as e:
            print(f"  ERROR fetching {name} at offset {offset}: {e}")
            break

        page = json.loads(raw)
        feats = page.get("features", [])
        if all_features is None:
            all_features = page
        else:
            all_features["features"].extend(feats)

        print(f"  {name}: fetched {len(feats)} features (offset {offset})")
        if len(feats) < page_size:
            break
        offset += page_size
        time.sleep(0.2)  # be polite to the county's server

    if all_features is None or not all_features.get("features"):
        print(f"  WARNING: no features retrieved for {name}, skipping write")
        return

    out_path.write_text(json.dumps(all_features), encoding="utf-8")
    print(f"  saved {len(all_features['features'])} features -> {out_path}")


def download_census_acs(year: int, state_fips: str, county_fips_list: list[str],
                         out_path: Path) -> None:
    """Pull ACS 5-year tract estimates: commute mode/time, population, land area.

    Requires a Census API key (verified 2026-07-30: anonymous requests now
    return an HTML "Missing Key" page instead of JSON, for every year tested).
    Get a free key at https://api.census.gov/data/key_signup.html and set
    CENSUS_API_KEY at the top of this file or as an environment variable.
    """
    variables = [
        "NAME",
        "B01003_001E",   # total population
        "B08303_001E",   # total commuters (travel time universe)
        "B08303_013E",   # commuters with travel time 60-89 min
        "B08303_012E",   # commuters with travel time 45-59 min
        "B08301_001E",   # total workers 16+ (means of transportation universe)
        "B08301_010E",   # workers who worked from home
    ]
    if not CENSUS_API_KEY:
        print(f"  SKIPPED ACS {year}: no Census API key set (see module docstring)")
        return

    base = f"https://api.census.gov/data/{year}/acs/acs5"
    all_rows = []
    header = None
    for county_fips in county_fips_list:
        params = urlencode({
            "get": ",".join(variables),
            "for": "tract:*",
            "in": f"state:{state_fips}+county:{county_fips}",
            "key": CENSUS_API_KEY,
        })
        url = f"{base}?{params}"
        try:
            raw = _fetch(url)
        except (HTTPError, URLError, OSError) as e:
            print(f"  ERROR fetching ACS {year} county {county_fips}: {e}")
            continue
        try:
            rows = json.loads(raw)
        except json.JSONDecodeError:
            print(f"  ERROR: ACS {year} county {county_fips} did not return JSON "
                  f"(check the API key / year is valid). First 200 bytes: {raw[:200]!r}")
            continue
        if header is None:
            header = rows[0]
        all_rows.extend(rows[1:])
        print(f"  ACS {year} county {county_fips}: {len(rows) - 1} tracts")
        time.sleep(0.2)

    if header is None:
        print(f"  WARNING: no ACS data retrieved for {year}, skipping write")
        return

    out_path.write_text(
        json.dumps([header] + all_rows, indent=2), encoding="utf-8"
    )
    print(f"  saved ACS {year} ({len(all_rows)} tracts) -> {out_path}")


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)

    print("Prince William County data-center layers (PWC GIS Open Data)")
    download_arcgis_layer(
        "PWC Data Center Buildings",
        "https://gisweb.pwcva.gov/arcgis/rest/services/Planning/Build_Out_Analysis/MapServer/9",
        OUT_DIR / "pwc_data_center_buildings.geojson",
    )
    download_arcgis_layer(
        "PWC Data Center Projects (campus polygons)",
        "https://gisweb.pwcva.gov/arcgis/rest/services/Planning/Build_Out_Analysis/MapServer/10",
        OUT_DIR / "pwc_data_center_projects.geojson",
    )
    download_arcgis_layer(
        "PWC Use Permits (all SUP/NCU cases, not data-center-specific)",
        "https://gisweb.pwcva.gov/arcgis/rest/services/Planning/Zoning/MapServer/6",
        OUT_DIR / "pwc_use_permits.geojson",
    )

    print("\nLoudoun County zoning (rezoning-case history; NOT data-center-specific)")
    download_arcgis_layer(
        "Loudoun Zoning",
        "https://logis.loudoun.gov/gis/rest/services/COL/Zoning/MapServer/3",
        OUT_DIR / "loudoun_zoning.geojson",
    )
    print("  NOTE: Loudoun has no confirmed open data-center-buildings/permits")
    print("  feature layer. See module docstring for manual-export options.")

    print("\nVDOT road route geometry (for AADT segment -> coordinates join)")
    download_arcgis_layer(
        "VDOT Routes",
        "https://services.arcgis.com/p5v98VHDX9Atv3l7/arcgis/rest/services/VDOT_Routes/FeatureServer/0",
        OUT_DIR / "vdot_routes.geojson",
        # Statewide layer is large -- restrict to the two counties by name.
        where="RTE_JURIS_PROPER_NM IN ('Loudoun County', 'Prince William County')",
    )

    print("\nCensus ACS 5-year estimates (commute + population), tract level")
    # Loudoun = 51107, Prince William = 51153 (Virginia state FIPS = 51)
    for year in (2013, 2019, 2023):
        download_census_acs(
            year=year,
            state_fips="51",
            county_fips_list=["107", "153"],
            out_path=OUT_DIR / f"acs5_{year}.json",
        )

    print("\nDone. Review External_Data/ before wiring into the main notebook --")
    print("in particular, confirm the VDOT Routes 'where' filter returned rows,")
    print("and decide how to handle the Loudoun data-center-permit gap.")


if __name__ == "__main__":
    main()
