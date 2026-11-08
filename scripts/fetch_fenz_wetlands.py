"""Put the national FENZ wetland layer on a region's 100 m grid, for regions
without a council wetland survey (Gisborne uses fetch_gdc_wetlands.py).

Source: Freshwater Ecosystems of New Zealand (FENZ), Department of
Conservation, current wetland extent with typology (layer
Current_wetlands_typology), as distributed with Burge (2022) "Data from: LiDAR
reveals drainage risks to wetlands are under-estimated",
doi:10.7931/f77d-vw23, Manaaki Whenua - Landcare Research datastore. CC BY 4.0.
Extent dates from about 1999-2003 and is coarser than council surveys: small
wetlands can be missing, and some mapped ones have since been drained.

Every FENZ wetland is a mapped natural wetland, so all count as natural.

Usage:
    python scripts/fetch_fenz_wetlands.py <name> [fenz.zip or folder]
        (default: downloads the zip to data/fenz/ if it isn't there)
Writes to data/env/<name>/ the same files as fetch_gdc_wetlands.py:
    wetlands.geojson         polygons (NZTM) with wl_class, wl_status, source
    wetland_class.tif        0 none, else code in CLASSES
    wetland_status.tif       0 none, else code in STATUSES
    distance_wetland.tif     metres to the nearest wetland
Needs pyshp (pip install pyshp) and rasterio.
"""
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import rasterio
import requests
import shapefile
from rasterio.features import rasterize
from scipy.ndimage import distance_transform_edt
from shapely.geometry import box, shape, mapping

ROOT = Path(__file__).resolve().parent.parent
URL = ("https://datastore.landcareresearch.co.nz/dataset/8699912c-6fe7-4a99-baa5-309f6abc148a/resource/"
       "4d1627be-99f2-4622-bb2f-1acaf6542a23/download/current_wetland_typologies.zip")
# Same codes as fetch_gdc_wetlands.py, plus FENZ's extra types
CLASSES = {"Shallow water": 1, "Marsh": 2, "Swamp": 3, "Seepage": 4, "Bog": 5,
           "Ephemeral": 6, "Saltmarsh": 7, "Fen": 8, "Pakihi": 9, "Gumland": 10, "Inland saline": 11}
STATUS = "FENZ current wetland"
STATUS_CODE = 7


def find_shp(arg):
    src = Path(arg) if arg else ROOT / "data" / "fenz"
    if src.suffix.lower() == ".zip":
        with zipfile.ZipFile(src) as z:
            z.extractall(src.parent)
        src = src.parent
    if src.is_dir() and not list(src.rglob("fenz_current_type.shp")):
        src.mkdir(parents=True, exist_ok=True)
        z = src / "current_wetland_typologies.zip"
        r = requests.get(URL, timeout=600)
        r.raise_for_status()
        z.write_bytes(r.content)
        with zipfile.ZipFile(z) as zz:
            zz.extractall(src)
    return next(p for p in src.rglob("fenz_current_type.shp") if "__MACOSX" not in p.parts)


def main():
    name = sys.argv[1]
    shp = find_shp(sys.argv[2] if len(sys.argv) > 2 else None)
    out = ROOT / "data" / "env" / name
    with rasterio.open(out / "elevation.tif") as ref:
        prof, shp_, transform, bounds = ref.profile.copy(), ref.shape, ref.transform, ref.bounds
    clip = box(*bounds)

    r = shapefile.Reader(str(shp.with_suffix("")), encoding="utf-8")
    feats = []
    for sr in r.iterShapeRecords(fields=["VegName"]):
        if not (clip.intersects(box(*sr.shape.bbox))):
            continue
        g = shape(sr.shape.__geo_interface__)
        if not g.is_valid:
            g = g.buffer(0)
        cls = (sr.record["VegName"] or "").strip()
        feats.append({"type": "Feature", "geometry": mapping(g),
                      "properties": {"wl_class": cls, "wl_status": STATUS, "confidence": None, "source": "FENZ",
                                     "Shape__Area": g.area}})
    gj = {"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "EPSG:2193"}}, "features": feats}
    (out / "wetlands.geojson").write_text(json.dumps(gj), encoding="utf-8")
    print(f"{len(feats):,} FENZ wetland polygons in the grid")

    # Big polygons first, so small wetlands drawn later are not overwritten.
    geoms = sorted(((f["geometry"], f["properties"]) for f in feats), key=lambda t: -t[1]["Shape__Area"])
    cls = rasterize([(g, CLASSES.get(p["wl_class"], 0)) for g, p in geoms if CLASSES.get(p["wl_class"])],
                    out_shape=shp_, transform=transform, fill=0, all_touched=True, dtype="uint8")
    status = np.where(cls > 0, STATUS_CODE, 0).astype("uint8")
    prof.update(dtype="uint8", nodata=255, compress="deflate")
    for fname, arr in [("wetland_class", cls), ("wetland_status", status)]:
        with rasterio.open(out / f"{fname}.tif", "w", **prof) as dst:
            dst.write(arr, 1)
        print(f"{fname}: {int((arr > 0).sum()):,} cells")

    # FENZ covers the whole country, so distance is valid everywhere on the grid
    dist = distance_transform_edt(cls == 0, sampling=abs(transform.a)).astype("float32")
    prof.update(dtype="float32", nodata=-9999)
    with rasterio.open(out / "distance_wetland.tif", "w", **prof) as dst:
        dst.write(dist, 1)
    print(f"distance_wetland: max {dist.max():.0f} m")


if __name__ == "__main__":
    main()
