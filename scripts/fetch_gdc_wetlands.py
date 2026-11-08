"""Fetch GDC's Regional Wetland Assessment 2022 (Morphum) and put it on the
region's 100 m grid.

Source: Gisborne District Council, "GDC Provisional Regional Wetland Assessment
2022 (Morphum Layer)", ArcGIS item 44bd61750e434993bced3ac0bc5e712b, CC BY 4.0.
A desktop assessment (aerial imagery + LiDAR), classified with NPS-FM and
Johnson & Gerbeaux (2004) wetland types. Not field-verified; see `confidence`.

Usage:
    python scripts/fetch_gdc_wetlands.py tairawhiti
Writes to data/env/<name>/:
    gdc_wetlands.geojson     the polygons (NZTM), all attributes
    wetland_class.tif        0 none, else code in CLASSES (cell touched by a wetland);
                             255 outside the region (not mapped)
    wetland_status.tif       0 none, else code in STATUSES; 255 outside the region
    distance_wetland.tif     metres to nearest natural wetland; -9999 outside the region
Needs data/env/<name>/region_osm_nominatim.json (the region boundary).
"""
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.features import rasterize
from rasterio.warp import transform_geom
from scipy.ndimage import distance_transform_edt

URL = ("https://services7.arcgis.com/8G10QCd84QpdcTJ9/ArcGIS/rest/services/"
       "GDC_Regional_Wetland_Assessment/FeatureServer/0/query")
CLASSES = {"Shallow water": 1, "Marsh": 2, "Swamp": 3, "Seepage": 4, "Bog": 5,
           "Ephemeral": 6, "Saltmarsh": 7, "Fen": 8}
STATUSES = {"NPS:FW Natural Wetland": 1, "NPS Natural": 2, "Induced": 3,
            "Pasture Exclusion": 4, "Pasture": 5, "Artificial": 6}
NATURAL = {"NPS:FW Natural Wetland", "NPS Natural", "Induced"}


def fetch():
    feats, offset = [], 0
    while True:
        r = requests.get(URL, params={
            "where": "1=1", "outFields": "*", "outSR": 2193, "f": "geojson",
            "resultOffset": offset, "resultRecordCount": 2000,
            "orderByFields": "OBJECTID"}, timeout=120)
        r.raise_for_status()
        page = r.json()["features"]
        feats += page
        if len(page) < 2000:
            return feats
        offset += len(page)


def main():
    name = sys.argv[1]
    out = Path(__file__).resolve().parent.parent / "data" / "env" / name
    feats = fetch()
    gj = {"type": "FeatureCollection",
          "crs": {"type": "name", "properties": {"name": "EPSG:2193"}},
          "features": feats}
    (out / "gdc_wetlands.geojson").write_text(json.dumps(gj), encoding="utf-8")
    print(f"{len(feats)} wetland polygons")

    with rasterio.open(out / "elevation.tif") as ref:
        prof, shape, transform = ref.profile.copy(), ref.shape, ref.transform
    # Big polygons first, so small wetlands drawn later are not overwritten.
    feats = sorted(feats, key=lambda f: -(f["properties"].get("Shape__Area") or 0))
    geoms = [(f["geometry"], f["properties"]) for f in feats if f["geometry"]]

    def burn(key, codes, only=None):
        shapes = [(g, codes[p[key]]) for g, p in geoms
                  if p.get(key) in codes and (only is None or p.get("wl_status") in only)]
        return rasterize(shapes, out_shape=shape, transform=transform,
                         fill=0, all_touched=True, dtype="uint8")

    # GDC only maps its own region. Outside it, "no wetland" means "not mapped",
    # so those cells are set to nodata. Region boundary: OSM via Nominatim,
    # saved as region_osm_nominatim.json when the region was set up.
    region = json.loads((out / "region_osm_nominatim.json").read_text())[0]["geojson"]
    inside = rasterize([(transform_geom("EPSG:4326", prof["crs"], region), 1)],
                       out_shape=shape, transform=transform, fill=0, dtype="uint8").astype(bool)

    prof.update(dtype="uint8", nodata=255, compress="deflate")
    for fname, arr in [("wetland_class", burn("wl_class", CLASSES)),
                       ("wetland_status", burn("wl_status", STATUSES))]:
        arr[~inside] = 255
        with rasterio.open(out / f"{fname}.tif", "w", **prof) as dst:
            dst.write(arr, 1)
        print(f"{fname}: {int(((arr > 0) & inside).sum()):,} cells")

    natural = burn("wl_class", CLASSES, only=NATURAL) > 0
    dist = distance_transform_edt(~natural, sampling=abs(transform.a)).astype("float32")
    dist[~inside] = -9999
    prof.update(dtype="float32", nodata=-9999)
    with rasterio.open(out / "distance_wetland.tif", "w", **prof) as dst:
        dst.write(dist, 1)
    print(f"distance_wetland: {int(natural.sum()):,} natural wetland cells; "
          f"max {dist[inside].max():.0f} m inside the region")


if __name__ == "__main__":
    main()
