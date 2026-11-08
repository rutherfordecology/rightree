"""Fetch selected NZEnvDS v1.1 layers (NZTM, 100 m) and clip them to a region.

Each layer is pulled from the remote zip with range requests, clipped to the
region's bounding box plus a margin, saved compressed, and the national copy is
deleted straight away, so disk use stays small.

NZEnvDS: McCarthy et al. 2021, NZ Journal of Ecology 45(2): 3440,
doi:10.20417/nzjecol.45.31; data doi:10.7931/m6rm-vz40. CC BY 4.0.

Usage:
    python scripts/fetch_env.py tairawhiti 177.12,-38.98,178.55,-37.53 50
        (name, lon/lat bbox, margin in km)
"""
import io
import shutil
import sys
import zipfile
from pathlib import Path

import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

sys.path.insert(0, str(Path(__file__).resolve().parent))
from remote_zip import HttpFile  # noqa: E402

URL = ("https://datastore.landcareresearch.co.nz/dataset/486076fc-878a-42af-b245-889e4dc3ad1e/"
       "resource/13360a13-c478-4d7d-980f-3db44a749fa7/download/nzenvds_v1.1_finalnztm.zip")
PREFIX = "NZEnvDS_V1.1_finalNZTM/final_layers_nztm/"

LAYERS = [
    # climate
    "temp_meanAnn", "temp_minColdMonth", "temp_gdd5", "precip_ann",
    "waterBalance_annDeficit", "vpd_oct", "solRad_meanAnn", "wind_meanAnn",
    # terrain
    "elevation", "slope_deg", "aspect_northness", "aspect_eastness",
    "topo_wetness", "topo_position", "distance_coast",
    # soil (Fundamental Soil Layers)
    "soil_drainage", "soil_pH", "soil_age", "soil_particleSize",
    "soil_acidP", "soil_calcium", "soil_induration", "soil_chemLims",
]


def main():
    name, bbox, margin_km = sys.argv[1], [float(v) for v in sys.argv[2].split(",")], float(sys.argv[3])
    root = Path(__file__).resolve().parent.parent
    out_dir = root / "data" / "env" / name
    tmp = root / "data" / "env" / "_tmp"
    out_dir.mkdir(parents=True, exist_ok=True)

    z = zipfile.ZipFile(io.BufferedReader(HttpFile(URL), buffer_size=8 << 20))
    for layer in LAYERS:
        dest = out_dir / f"{layer}.tif"
        if dest.exists():
            print(f"have {layer}", flush=True)
            continue
        member = PREFIX + layer + ".tif"
        print(f"fetching {layer} ({z.getinfo(member).file_size / 1e6:.0f} MB)", flush=True)
        src_path = Path(z.extract(member, tmp))
        with rasterio.open(src_path) as src:
            l, b, r, t = transform_bounds("EPSG:4326", src.crs, *bbox)
            m = margin_km * 1000
            win = from_bounds(l - m, b - m, r + m, t + m, src.transform).round_offsets().round_lengths()
            win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
            data = src.read(1, window=win)
            prof = src.profile.copy()
            prof.update(width=win.width, height=win.height, transform=src.window_transform(win),
                        compress="deflate", tiled=True, blockxsize=256, blockysize=256, BIGTIFF="NO")
        with rasterio.open(dest, "w", **prof) as dst:
            dst.write(data, 1)
        shutil.rmtree(tmp)
        print(f"  saved {dest.name}: {win.width}x{win.height} cells, {dest.stat().st_size / 1e6:.1f} MB", flush=True)
    print("done")


if __name__ == "__main__":
    main()
