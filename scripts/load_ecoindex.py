"""Grid Eco-index's Ecosystem Projector (potential natural ecosystems) onto a
region's 100 m grid.

The layer is CC BY 4.0 but downloading it needs a (free) Koordinates sign-in,
so export it yourself from
https://eco-index.koordinates.com/layer/120435-eco-index-ecosystem-projector-for-nz/
as a Shapefile or GeoPackage in NZTM, cropped to the region, and pass the zip.

Usage:
    python scripts/load_ecoindex.py <export.zip | folder with the .shp> [region]

Writes data/env/<region>/potential_ecosystem.tif (0 = none) and
potential_ecosystem_classes.json (code -> name and group). Then rerun
scripts/make_tiles.py.
Needs pyshp (pip install pyshp) and rasterio; only run locally.
"""
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import rasterio
import shapefile
from rasterio.features import rasterize

ROOT = Path(__file__).resolve().parent.parent


def main():
    src = Path(sys.argv[1])
    region = sys.argv[2] if len(sys.argv) > 2 else "tairawhiti"
    if src.suffix.lower() == ".zip":
        out = ROOT / "data" / "ecoindex"
        out.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(src) as z:
            z.extractall(out)
        src = out
    shp = next(src.glob("*.shp")) if src.is_dir() else src
    env = ROOT / "data" / "env" / region
    prj = shp.with_suffix(".prj").read_text()
    assert "Transverse_Mercator" in prj and "173" in prj, "export the layer in NZTM (EPSG:2193)"

    r = shapefile.Reader(str(shp.with_suffix("")), encoding="utf-8")
    names = [f[0] for f in r.fields[1:]]
    classes, shapes = {}, []
    for sr in r.iterShapeRecords():
        rec = dict(zip(names, sr.record))
        name, group = rec["ExpectedEc"].strip(), (rec.get("Aggregated") or "").strip().replace("Lowland-forest", "Lowland forest")
        if not name or name.lower() == "unclassified":
            continue
        code = next((k for k, v in classes.items() if v["name"] == name), len(classes) + 1)
        classes[code] = {"name": name, "group": group}
        shapes.append((sr.shape.__geo_interface__, code))
    assert len(classes) < 255

    with rasterio.open(env / "elevation.tif") as ref:
        prof = ref.profile
        grid = rasterize(shapes, out_shape=ref.shape, transform=ref.transform, fill=0, dtype="uint8")
    prof.update(dtype="uint8", nodata=0, compress="deflate")
    with rasterio.open(env / "potential_ecosystem.tif", "w", **prof) as dst:
        dst.write(grid, 1)
    (env / "potential_ecosystem_classes.json").write_text(
        json.dumps({str(k): v for k, v in classes.items()}, ensure_ascii=False, indent=1), encoding="utf-8")
    vals, n = np.unique(grid[grid > 0], return_counts=True)
    print(f"{region}: {len(classes)} ecosystem types, {int(n.sum()):,} cells gridded")
    for v, c in sorted(zip(vals, n), key=lambda t: -t[1])[:8]:
        print(f"  {classes[int(v)]['name']}: {c:,} ha")


if __name__ == "__main__":
    main()
