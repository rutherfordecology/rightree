"""Fetch LCDB v6 (1996-2023) polygons for a region from LRIS and put the
current (2023) land cover on the region's 100 m grid.

Source: Manaaki Whenua - Landcare Research, Land Cover Database v6.0,
LRIS layer 123148, CC BY 4.0. Mapped at about 1 ha minimum.

Needs an LRIS API key: put it on one line in `rightree/.lris_key` (gitignored)
or in the LRIS_KEY environment variable.

Usage:
    python scripts/fetch_lcdb.py tairawhiti 177.12,-38.98,178.55,-37.53 50
        (name, lon/lat bbox, margin in km; same as fetch_env.py)
Writes to data/env/<name>/:
    lcdb_v6.geojson     polygons (NZTM), all attributes
    lcdb_class.tif      Class_2023 code (0 = no data); codes in lcdb_classes.json
    lcdb_classes.json   code -> class name
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.features import rasterize
from rasterio.warp import transform_bounds

LAYER = 123148
ROOT = Path(__file__).resolve().parent.parent
PAGE = 5000


def key():
    k = os.environ.get("LRIS_KEY")
    if not k and (ROOT / ".lris_key").exists():
        k = (ROOT / ".lris_key").read_text().strip()
    if not k:
        sys.exit("No LRIS key: put it in rightree/.lris_key or set LRIS_KEY.")
    return k


def fetch(bbox_nztm):
    url = f"https://lris.scinfo.org.nz/services;key={key()}/wfs/layer-{LAYER}/"
    feats, start = [], 0
    while True:
        r = requests.get(url, params={
            "service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typeNames": f"layer-{LAYER}", "outputFormat": "json",
            "srsName": "EPSG:2193", "count": PAGE, "startIndex": start,
            "bbox": ",".join(f"{v:.0f}" for v in bbox_nztm) + ",EPSG:2193",
        }, timeout=300)
        if r.status_code != 200:
            # Never print the URL: it contains the key.
            sys.exit(f"LRIS returned HTTP {r.status_code}: {r.text[:300]}")
        page = r.json().get("features", [])
        feats += page
        print(f"  {len(feats):,} polygons", flush=True)
        if len(page) < PAGE:
            return feats
        start += len(page)


def main():
    name, bbox, margin_km = sys.argv[1], [float(v) for v in sys.argv[2].split(",")], float(sys.argv[3])
    out = ROOT / "data" / "env" / name
    with rasterio.open(out / "elevation.tif") as ref:
        prof, shape, transform, crs = ref.profile.copy(), ref.shape, ref.transform, ref.crs
    l, b, r, t = transform_bounds("EPSG:4326", crs, *bbox)
    m = margin_km * 1000
    feats = fetch((l - m, b - m, r + m, t + m))

    gj = {"type": "FeatureCollection",
          "crs": {"type": "name", "properties": {"name": "EPSG:2193"}},
          "features": feats}
    (out / "lcdb_v6.geojson").write_text(json.dumps(gj), encoding="utf-8")

    p0 = feats[0]["properties"]
    code_f = next(k for k in p0 if k.lower() == "class_2023")
    name_f = next(k for k in p0 if k.lower() == "name_2023")
    names = {}
    shapes = []
    for f in feats:
        p = f["properties"]
        if f["geometry"] and p.get(code_f) is not None:
            c = int(p[code_f])
            names[c] = p.get(name_f)
            shapes.append((f["geometry"], c))
    arr = rasterize(shapes, out_shape=shape, transform=transform, fill=0, dtype="uint8")
    prof.update(dtype="uint8", nodata=0, compress="deflate")
    with rasterio.open(out / "lcdb_class.tif", "w", **prof) as dst:
        dst.write(arr, 1)
    (out / "lcdb_classes.json").write_text(json.dumps(dict(sorted(names.items())), indent=1), encoding="utf-8")

    vals, counts = np.unique(arr[arr > 0], return_counts=True)
    print(f"{len(feats):,} polygons, {len(names)} classes")
    for v, n in sorted(zip(vals, counts), key=lambda x: -x[1])[:15]:
        print(f"  {n * 0.01:9.0f} km2  {v:3d} {names.get(int(v))}")


if __name__ == "__main__":
    main()
