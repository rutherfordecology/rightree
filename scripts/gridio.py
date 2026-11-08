"""Read the region's grids from small tiles (made by scripts/make_tiles.py).

The model only ever needs the cells under a site, so it reads just the
tiles those cells fall in. That keeps a prediction in the browser to a few
megabytes of downloads instead of the whole region. Locally the tiles are
plain files; in the browser FETCH is set to a function that downloads one.

data/env/<region>/tiles/grid.json   shape, transform, tile size, layer dtypes
data/env/<region>/tiles/<layer>/<tile row>_<tile col>.bin   zlib of the raw tile
data/env/<region>/region_stats.json   each layer's regional range (for scaling)
"""
import json
import zlib
from pathlib import Path

import numpy as np

FETCH = None            # browser: function(path) -> bytes
_tiles = {}             # (dir, layer, tr, tc) -> array, kept between runs


def read_bytes(path):
    path = Path(path)
    if path.exists():
        return path.read_bytes()
    if FETCH is not None:
        return FETCH(path.as_posix())
    raise FileNotFoundError(path)


class Grid:
    def __init__(self, env_dir):
        self.dir = Path(env_dir) / "tiles"
        m = json.loads(read_bytes(self.dir / "grid.json"))
        self.shape = tuple(m["shape"])
        self.x0, self.dx, self.y0, self.dy = m["transform"]   # dy is negative
        self.T = m["tile"]
        self.layers = m["layers"]                          # name -> {dtype, nodata}

    def rowcol(self, x, y):
        return (np.floor((np.asarray(y) - self.y0) / self.dy).astype(int),
                np.floor((np.asarray(x) - self.x0) / self.dx).astype(int))

    def centres(self, rows, cols):
        return self.x0 + (np.asarray(cols) + 0.5) * self.dx, self.y0 + (np.asarray(rows) + 0.5) * self.dy

    def cells_in(self, poly):
        """Row, col of every cell whose centre is inside the polygon (in the
        grid's CRS), the same rule as rasterio's rasterize."""
        import shapely
        minx, miny, maxx, maxy = poly.bounds
        r0, c0 = self.rowcol(minx, maxy)
        r1, c1 = self.rowcol(maxx, miny)
        r0, c0 = max(r0, 0), max(c0, 0)
        r1, c1 = min(r1, self.shape[0] - 1), min(c1, self.shape[1] - 1)
        if r1 < r0 or c1 < c0:
            return np.array([], int), np.array([], int)
        rr, cc = np.mgrid[r0:r1 + 1, c0:c1 + 1]
        rr, cc = rr.ravel(), cc.ravel()
        x, y = self.centres(rr, cc)
        keep = shapely.contains_xy(poly, x, y)
        return rr[keep], cc[keep]

    def cell_boxes(self, rows, cols):
        import shapely
        x, y = self.centres(rows, cols)
        h = abs(self.dx) / 2
        return shapely.box(x - h, y - h, x + h, y + h)

    def tile(self, layer, tr, tc):
        key = (str(self.dir), layer, tr, tc)
        if key not in _tiles:
            lay = self.layers[layer]
            h = min(self.T, self.shape[0] - tr * self.T)
            w = min(self.T, self.shape[1] - tc * self.T)
            raw = zlib.decompress(read_bytes(self.dir / layer / f"{tr}_{tc}.bin"))
            _tiles[key] = np.frombuffer(raw, dtype=lay["dtype"]).reshape(h, w)
        return _tiles[key]

    def values(self, layer, rows, cols):
        """Values of one layer at the given cells, in the layer's own dtype."""
        rows, cols = np.asarray(rows), np.asarray(cols)
        out = np.empty(len(rows), dtype=self.layers[layer]["dtype"])
        tr, tc = rows // self.T, cols // self.T
        for a, b in set(zip(tr.tolist(), tc.tolist())):
            sel = (tr == a) & (tc == b)
            out[sel] = self.tile(layer, a, b)[rows[sel] - a * self.T, cols[sel] - b * self.T]
        return out

    def float_values(self, layer, rows, cols):
        """Values as float64 with no-data as NaN."""
        a = self.values(layer, rows, cols).astype("float64")
        nd = self.layers[layer]["nodata"]
        if nd is not None and not np.isnan(nd):
            a[a == nd] = np.nan
        return a
