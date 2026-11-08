"""Cut a region's grids into 256-cell tiles and save the regional ranges the
model scales by. Run after the grids change (needs rasterio; predict.py and
the browser don't).

Usage:
    python scripts/make_tiles.py [region]        # default: every region
"""
import json
import shutil
import sys
import zlib
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.warp import transform_geom

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gridio  # noqa: E402
from predict import ROOT, VARS, region_stats  # noqa: E402

TILE = 256
LAYERS = VARS + ["lcdb_class", "wetland_status"]


def main():
    env_root = ROOT / "data" / "env"
    regions = sys.argv[1:] or [p.name for p in env_root.iterdir() if (p / "region_osm_nominatim.json").exists()]
    for region in regions:
        env_dir = env_root / region
        out = env_dir / "tiles"
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir()
        meta = None
        for layer in LAYERS:
            with rasterio.open(env_dir / f"{layer}.tif") as s:
                a, t, nd = s.read(1), s.transform, s.nodata
                if meta is None:
                    assert s.crs.to_epsg() == 2193, "grids must be NZTM"
                    meta = {"shape": list(a.shape), "transform": [t.c, t.a, t.f, t.e], "tile": TILE, "layers": {}}
                    elev_t = t
            meta["layers"][layer] = {"dtype": str(a.dtype), "nodata": None if nd is None or np.isnan(nd) else float(nd)}
            (out / layer).mkdir()
            for tr in range(0, a.shape[0], TILE):
                for tc in range(0, a.shape[1], TILE):
                    tile = np.ascontiguousarray(a[tr:tr + TILE, tc:tc + TILE])
                    (out / layer / f"{tr // TILE}_{tc // TILE}.bin").write_bytes(zlib.compress(tile.tobytes(), 9))
        (out / "grid.json").write_text(json.dumps(meta), encoding="utf-8")

        # Regional ranges, from land cells inside the region boundary
        with rasterio.open(env_dir / "elevation.tif") as s:
            assert s.transform == elev_t
            elev = s.read(1)
        geo = json.loads((env_dir / "region_osm_nominatim.json").read_text())[0]["geojson"]
        inside = rasterize([(transform_geom("EPSG:4326", "EPSG:2193", geo), 1)], out_shape=elev.shape,
                           transform=elev_t, fill=0, dtype="uint8").astype(bool) & np.isfinite(elev)
        r, c = np.nonzero(inside)
        lo, scale = region_stats(gridio.Grid(env_dir), r, c)
        (env_dir / "region_stats.json").write_text(json.dumps({"lo": lo.to_dict(), "scale": scale.to_dict()}, indent=1),
                                                   encoding="utf-8")
        n = sum(1 for _ in out.rglob("*.bin"))
        mb = sum(p.stat().st_size for p in out.rglob("*.bin")) / 1e6
        print(f"{region}: {n} tiles, {mb:.1f} MB")


if __name__ == "__main__":
    main()
