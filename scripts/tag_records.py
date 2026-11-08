"""Attach land cover, wetland and environmental values to every cleaned record.

- LCDB v6: exact polygon. Cover at the LCDB date nearest the record's year
  (1996 for anything older, which is most NVS plots), plus 2023 cover.
- GDC wetlands: exact polygon (class, status, confidence), inside the region.
- Environmental layers: value of the 100 m cell the record falls in.

Usage:
    python scripts/tag_records.py tairawhiti
Writes data/records_<name>_tagged.csv.gz
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import shapely
from rasterio.warp import transform
from scipy.ndimage import distance_transform_edt

LCDB_YEARS = [1996, 2001, 2008, 2012, 2018, 2023]
WOODY = {"Indigenous Forest", "Broadleaved Indigenous Hardwoods", "Manuka and/or Kanuka",
         "Matagouri or Grey Scrub", "Sub Alpine Shrubland", "Gorse and/or Broom", "Mixed Exotic Shrubland"}
WOODY_MAX_M = 200   # dist_woody_m is blank beyond this


def load_polys(path, fields):
    feats = [f for f in json.loads(Path(path).read_text(encoding="utf-8"))["features"] if f["geometry"]]
    geoms = shapely.from_geojson([json.dumps(f["geometry"]) for f in feats])
    props = pd.DataFrame([{k: f["properties"].get(k) for k in fields} for f in feats])
    return shapely.STRtree(geoms), geoms, props


def hit(tree, pts):
    """Index of the polygon containing each point, or -1."""
    pi, gi = tree.query(pts, predicate="within")
    out = np.full(len(pts), -1)
    out[pi] = gi
    return out


def main():
    name = sys.argv[1]
    root = Path(__file__).resolve().parent.parent
    env = root / "data" / "env" / name
    df = pd.read_csv(root / "data" / f"records_{name}.csv.gz", low_memory=False)

    x, y = transform("EPSG:4326", "EPSG:2193", df["decimalLongitude"].tolist(), df["decimalLatitude"].tolist())
    pts = shapely.points(np.array(x), np.array(y))

    # LCDB
    fields = [f"Name_{yr}" for yr in LCDB_YEARS] + [f"Wetland_{str(yr)[2:]}" for yr in LCDB_YEARS]
    tree, geoms, props = load_polys(env / "lcdb_v6.geojson", fields)
    i = hit(tree, pts)
    yr = df["year"].fillna(1996).to_numpy()
    nearest = np.array(LCDB_YEARS)[np.abs(yr[:, None] - np.array(LCDB_YEARS)[None, :]).argmin(axis=1)]
    df["lcdb_year_used"] = nearest
    df["lcdb_at_record"] = [props.at[j, f"Name_{n}"] if j >= 0 else None for j, n in zip(i, nearest)]
    df["lcdb_2023"] = [props.at[j, "Name_2023"] if j >= 0 else None for j in i]
    df["lcdb_wetland_at_record"] = [props.at[j, f"Wetland_{str(n)[2:]}"] if j >= 0 else None for j, n in zip(i, nearest)]

    # Distance to the nearest woody cover at the same LCDB date. A record mapped
    # as pasture but a few metres from bush is usually in or at the edge of a
    # remnant LCDB didn't map (1 ha minimum), so predict.py won't count it as
    # open ground.
    df["dist_woody_m"] = np.nan
    for yr_ in LCDB_YEARS:
        sel = np.flatnonzero(nearest == yr_)
        if not len(sel):
            continue
        woody = geoms[props[f"Name_{yr_}"].isin(WOODY).to_numpy()]
        (qi, _), d = shapely.STRtree(woody).query_nearest(pts[sel], max_distance=WOODY_MAX_M, return_distance=True)
        df.loc[df.index[sel[qi]], "dist_woody_m"] = d

    # GDC wetlands
    tree, _, props = load_polys(env / "gdc_wetlands.geojson", ["wl_class", "wl_status", "confidence"])
    i = hit(tree, pts)
    for f in ["wl_class", "wl_status", "confidence"]:
        df[f"gdc_{f}"] = [props.at[j, f] if j >= 0 else None for j in i]

    # Environmental rasters. A record in a no-data cell (coastal records often
    # fall in a cell the grid treats as sea) takes the nearest valid cell
    # within FILL_M, so dune and rocky-shore records keep their environment.
    FILL_M = 300
    skip = {"lcdb_class", "wetland_class", "wetland_status"}
    for tif in sorted(env.glob("*.tif")):
        if tif.stem in skip:
            continue
        with rasterio.open(tif) as s:
            a = s.read(1).astype("float64")
            if s.nodata is not None:
                a[a == s.nodata] = np.nan
            if tif.stem.startswith("soil_"):
                a[a == 0] = np.nan          # FSL 0 = no data
            rr, cc = rasterio.transform.rowcol(s.transform, x, y)
            rr, cc = np.clip(rr, 0, s.height - 1), np.clip(cc, 0, s.width - 1)
            bad = np.isnan(a)
            dist, (ir, ic) = distance_transform_edt(bad, return_indices=True)
            filled = a[ir, ic]
            filled[dist * abs(s.transform.a) > FILL_M] = np.nan
            if tif.stem == "distance_wetland":
                filled = a                  # outside the GDC region stays unknown
        df[f"env_{tif.stem}"] = filled[rr, cc]

    out = root / "data" / f"records_{name}_tagged.csv.gz"
    df.to_csv(out, index=False)
    print(f"Wrote {out.name}: {len(df):,} records, {df.shape[1]} columns")

    print("\nLand cover at time of record (records / species / NVS visits):")
    t = df.groupby("lcdb_at_record").agg(records=("species", "size"), species=("species", "nunique"),
                                         nvs_visits=("visit", lambda s: s[df.loc[s.index, "source"] == "NVS"].nunique()))
    print(t.sort_values("records", ascending=False).head(15).to_string())
    print(f"\nIn a GDC wetland polygon: {df['gdc_wl_class'].notna().sum():,} records, "
          f"{df.loc[df['gdc_wl_class'].notna(), 'species'].nunique()} species")
    print(f"Records missing any env value: {df.filter(like='env_').drop(columns='env_distance_wetland').isna().any(axis=1).sum()}")


if __name__ == "__main__":
    main()
