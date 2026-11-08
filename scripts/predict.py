"""Predict expected native species for a polygon from environmental analogues.

1. Units. The polygon's 100 m cells are clustered on their environment into
   1-4 units (k-means; one unit unless the split is clear).
2. Distance. Gower: each layer scaled by its range across the region, mean
   absolute difference within three equally weighted groups (climate,
   terrain, soil), plus distance to wetland inside the GDC region. A site is
   only an analogue within MAX_D, and is vetoed outright if temperature,
   cold-month minimum, rainfall or distance to coast differs by more than
   VETO of the range.
3. Plot evidence (NVS). For each unit and each successional stage, the
   closest (up to K_PLOTS) NVS plot visits recorded in that stage (land cover
   at the time of the plot). A species' frequency is the share of those plots
   that recorded it. Plots list every species present, so a low share means
   absent from similar plots, not just unrecorded. Needs MIN_PLOTS plots.
4. Observation evidence (iNaturalist, herbaria). The closest presence-only
   records in each stage, as a share of those observations. Biased towards
   easily seen species; treat as supporting evidence. With too few plots and
   too few observations the report says so instead of giving a list.
5. Wetland. If a unit contains a natural wetland (GDC), species recorded
   inside natural GDC wetland polygons at the most similar sites are listed
   separately.

Usage:
    python scripts/predict.py tairawhiti <site-name> <polygon.kml|.kmz|.geojson | WKT in lon/lat>
Writes data/predictions/<site-name>/: report.md, species.csv, units.geojson
"""
import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

import gridio
import nztm

ROOT = Path(__file__).resolve().parent.parent
GZIP = bytes([0x1F, 0x8B])

GROUPS = {
    "climate": ["temp_meanAnn", "temp_minColdMonth", "precip_ann", "waterBalance_annDeficit",
                "vpd_oct", "solRad_meanAnn", "wind_meanAnn"],
    "terrain": ["slope_deg", "aspect_northness", "topo_wetness", "topo_position", "distance_coast"],
    # soil_chemLims left out: 99.4% one class in Gisborne, so it carries no signal
    "soil": ["soil_drainage", "soil_pH", "soil_age", "soil_particleSize", "soil_acidP",
             "soil_calcium", "soil_induration"],
}
SOIL = set(GROUPS["soil"])
WATER = "distance_wetland"          # log-transformed; only inside the GDC region
VARS = [v for g in GROUPS.values() for v in g] + [WATER]
WEIGHTS = np.array([1 / len(g) for g in GROUPS.values() for _ in g] + [0.5])

STAGES = {
    "Mature forest": {"Indigenous Forest"},
    "Regenerating (hardwoods, mānuka/kānuka, scrub)": {
        "Broadleaved Indigenous Hardwoods", "Manuka and/or Kanuka", "Matagouri or Grey Scrub",
        "Gorse and/or Broom", "Mixed Exotic Shrubland", "Fernland", "Sub Alpine Shrubland"},
    "Open (grassland, riverbed, coast)": {
        "High Producing Exotic Grassland", "Low Producing Grassland", "Tall Tussock Grassland",
        "Depleted Grassland", "Herbaceous Freshwater Vegetation", "Herbaceous Saline Vegetation",
        "Gravel and Rock", "Sand and Gravel", "River", "Landslide", "Flaxland"},
}
K_PLOTS, K_OBS = 20, 100
MAX_D = 0.15        # Gower distance (share of each layer's range) for a usable analogue
# Veto: an average hides one big difference (dune plants 50 km inland), so an
# analogue is also rejected if any of these differs by more than VETO of its range.
KEY_VARS = ["temp_meanAnn", "temp_minColdMonth", "precip_ann", "distance_coast"]
VETO = 0.25
MIN_PLOTS = 5       # fewer close plots than this: no plot-based list for that stage
MIN_OBS = 20        # ...and fewer close observations than this: fall back
# Fallback when a stage has no close analogues (the flats, where little native
# vegetation is left): nearest sites that still pass the veto, flagged.
FALLBACK_D = 0.35
MIN_PLOTS_FB, MIN_OBS_FB = 3, 10
# Units: split only if each unit holds at least UNIT_MIN_SHARE of the cells and
# every pair is at least UNIT_MIN_D apart (a third of the analogue threshold).
UNIT_MIN_D, UNIT_MIN_SHARE = 0.05, 0.10
MAX_CELLS = 20_000      # largest area accepted, in 100 m cells (ha)
ON_SITE_BUFFER_M = 100  # records this close to the site are left out of the evidence
NATURAL_WETLAND = {"NPS:FW Natural Wetland", "NPS Natural", "Induced"}


def transform_vals(df):
    """Log-transform distances so 100 m vs 1 km matters more than 10 vs 11 km."""
    out = df.copy()
    for c in ("distance_coast", WATER):
        if c in out:
            out[c] = np.log1p(out[c].clip(lower=0))
    for c in SOIL & set(out.columns):
        out.loc[out[c] == 0, c] = np.nan      # FSL 0 = no data (water, towns)
    return out


def read_kml(text):
    """Union of every Polygon in a KML (e.g. an Occurd area export), holes kept."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(text)
    local = lambda el: el.tag.rsplit("}", 1)[-1]

    def ring(el):
        coords = next(e for e in el.iter() if local(e) == "coordinates")
        return [tuple(map(float, c.split(",")[:2])) for c in coords.text.split()]

    polys = []
    for pg in (e for e in root.iter() if local(e) == "Polygon"):
        outer = [ring(c) for c in pg if local(c) == "outerBoundaryIs"][0]
        holes = [ring(c) for c in pg if local(c) == "innerBoundaryIs"]
        polys.append(shapely.Polygon(outer, holes))
    if not polys:
        sys.exit("No polygons found in the KML.")
    return shapely.make_valid(shapely.union_all(polys))


def read_polygon(arg):
    p = Path(arg)
    if p.exists() and p.suffix.lower() == ".kml":
        return read_kml(p.read_bytes())
    if p.exists() and p.suffix.lower() == ".kmz":
        import zipfile
        with zipfile.ZipFile(p) as z:
            return read_kml(z.read(next(n for n in z.namelist() if n.endswith(".kml"))))
    if p.exists():
        gj = json.loads(p.read_text(encoding="utf-8"))
        geoms = [f["geometry"] for f in gj["features"]] if gj.get("type") == "FeatureCollection" else [gj.get("geometry", gj)]
        return shapely.union_all([shapely.from_geojson(json.dumps(g)) for g in geoms])
    return shapely.from_wkt(arg)


def env_stack(grid, rows, cols):
    """Values of every VAR at the given cells."""
    return transform_vals(pd.DataFrame({v: grid.float_values(v, rows, cols) for v in VARS}))


def region_stats(grid, r, c, n=200_000, seed=1):
    """Each layer's range across the region's land cells (r, c). Run once by
    make_tiles.py and saved to region_stats.json."""
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(r), size=min(n, len(r)), replace=False)
    sample = env_stack(grid, r[pick], c[pick])
    # Gower-style scaling: each layer by its range across the region
    # (1st-99th percentile, so a few extreme cells don't set the scale).
    lo, hi = sample.quantile(0.01), sample.quantile(0.99)
    return lo, (hi - lo).replace(0, 1)


def load_region_stats(env_dir):
    s = json.loads(gridio.read_bytes(env_dir / "region_stats.json"))
    return pd.Series(s["lo"])[VARS], pd.Series(s["scale"])[VARS]


def gower(a, b):
    """Gower distance between two vectors, no veto."""
    ok = ~(np.isnan(a) | np.isnan(b))
    return float((np.abs(a - b)[ok] * WEIGHTS[ok]).sum() / max(WEIGHTS[ok].sum(), 1e-9))


def dist(a, B):
    """Gower distance from vector a to rows of B: weighted mean absolute
    difference in range units, ignoring missing values. 0 = identical,
    0.1 = typically a tenth of each layer's regional range apart."""
    diff = np.abs(B - a)
    ok = ~np.isnan(diff)
    w = np.where(ok, WEIGHTS, 0.0)
    d = np.nansum(np.where(ok, diff, 0.0) * w, axis=1) / np.maximum(w.sum(axis=1), 1e-9)
    key = [VARS.index(v) for v in KEY_VARS]
    # missing key values count against the analogue
    vetoed = np.nan_to_num(diff[:, key], nan=np.inf).max(axis=1) > VETO
    return np.where(vetoed, np.inf, d)


def within(d, limit, k):
    """Indices of the k smallest finite distances that are <= limit."""
    order = np.argsort(d)
    return order[d[order] <= limit][:k]


def clean_name(n):
    """'Lecanopteris pustulata (G.Forst.) Perrie & Brownsey subsp. pustulata'
    -> 'Lecanopteris pustulata subsp. pustulata'."""
    t = str(n).split()
    out, i = t[:2], 2
    while i < len(t):
        if t[i] in ("subsp.", "var.", "f.") and i + 1 < len(t):
            out += t[i:i + 2]
            i += 2
        else:
            i += 1
    return " ".join(out)


def stage_of(cover):
    for s, covers in STAGES.items():
        if cover in covers:
            return s
    return None


MATURE, REGEN, OPEN = list(STAGES)


def load_growth_forms():
    """(form, habitat) lookup by name: species entry first, then genus."""
    gf = json.loads((ROOT / "config" / "growth_forms.json").read_text(encoding="utf-8"))

    def lookup(name):
        return gf["species"].get(" ".join(name.split()[:2])) or gf["genera"].get(name.split()[0])
    return lookup


def load_layers():
    """Layers (canopy, subcanopy, understorey, ground, climber, epiphyte) a
    plant can fill: species or genus override, else the default for its form."""
    gf = json.loads((ROOT / "config" / "growth_forms.json").read_text(encoding="utf-8"))
    form = load_growth_forms()

    def layers(name):
        o = gf["layers"].get(" ".join(name.split()[:2])) or gf["layers"].get(name.split()[0])
        if o:
            return o
        f = form(name)
        return gf["layer_of_form"].get(f[0], []) if f else []
    return layers


CANOPY = {"canopy tree"}
WOODY_FORMS = {"canopy tree", "small tree", "shrub", "tree fern"}
MIN_CANOPY_GENERA, MIN_WOODY_GENERA = 3, 4
EDGE_M = 50   # an open-mapped observation this close to bush or scrub isn't counted as open


def restage_plots(stage, visit_species, gf):
    """LCDB's minimum mapping unit is 1 ha, so a plot in a forest remnant can
    sit in polygons mapped as pasture. Plots that LCDB calls open (or an
    excluded cover) but that record several canopy-tree genera are mature
    forest; with several woody genera, regenerating."""
    out, n = stage.copy(), 0
    for v, st in stage.items():
        if st in (MATURE, REGEN):
            continue
        forms = {}
        for s in visit_species[v]:
            f = gf(s)
            if f:
                forms[s.split()[0]] = f[0]
        canopy = sum(f in CANOPY for f in forms.values())
        woody = sum(f in WOODY_FORMS for f in forms.values())
        new = MATURE if canopy >= MIN_CANOPY_GENERA else REGEN if woody >= MIN_WOODY_GENERA else st
        if new != st:
            out[v], n = new, n + 1
    return out, n


def main():
    region, site, poly_arg = sys.argv[1], sys.argv[2], sys.argv[3]
    env_dir = ROOT / "data" / "env" / region
    out_dir = ROOT / "data" / "predictions" / site
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── cells of the polygon ──────────────────────────────────────────────
    poly_ll = read_polygon(poly_arg)
    grid = gridio.Grid(env_dir)
    poly = nztm.geom_to_nztm(poly_ll)          # the grids are NZTM (EPSG:2193)
    rows, cols = grid.cells_in(poly)
    if len(rows) == 0:  # tiny polygon: take the cell under its centre
        c = poly.centroid
        rr, cc = grid.rowcol(c.x, c.y)
        if not (0 <= rr < grid.shape[0] and 0 <= cc < grid.shape[1]):
            sys.exit("The area is outside the region.")
        rows, cols = np.array([rr]), np.array([cc])
    if len(rows) > MAX_CELLS:
        sys.exit(f"The area is too large: {len(rows):,} ha. The limit is {MAX_CELLS:,} ha; "
                 "split it into smaller areas.")
    cells = env_stack(grid, rows, cols)
    land = cells[KEY_VARS].notna().all(axis=1).to_numpy()    # drop sea and no-data cells
    if not land.any():
        sys.exit("The polygon has no land cells with environmental data.")
    if (~land).any():
        print(f"Dropped {int((~land).sum())} cells with no environmental data (sea or outside the layers).")
    rows, cols, cells = rows[land], cols[land], cells[land].reset_index(drop=True)
    mu, sd = load_region_stats(env_dir)
    Z = ((cells - mu) / sd)[VARS].to_numpy()

    # ── units ─────────────────────────────────────────────────────────────
    valid = ~np.isnan(Z[:, :len(VARS) - 1]).any(axis=1)
    labels = np.zeros(len(Z), dtype=int)
    if valid.sum() >= 50:
        Zv = np.nan_to_num(Z[valid] * np.sqrt(WEIGHTS))
        best_k, best_s = 1, 0.25          # split only if the silhouette clears 0.25
        for k in (2, 3, 4):
            if valid.sum() < 25 * k:
                break
            lab = KMeans(k, n_init=10, random_state=1).fit_predict(Zv)
            s = silhouette_score(Zv, lab, sample_size=min(3000, len(Zv)), random_state=1)
            # A clean split can still be a trivial one. Keep it only if every
            # unit is a real share of the site and every pair of units is far
            # enough apart to change which analogues are picked.
            meds = [np.nanmedian(Z[valid][lab == j], axis=0) for j in range(k)]
            gap = min(gower(meds[i], meds[j]) for i in range(k) for j in range(i + 1, k))
            small = np.bincount(lab).min() / len(lab)
            print(f"  k={k}: silhouette {s:.2f}, smallest unit {small:.0%}, closest units {gap:.3f} apart")
            if gap < UNIT_MIN_D or small < UNIT_MIN_SHARE:
                continue
            if s > best_s:
                best_k, best_s, best_lab = k, s, lab
        if best_k > 1:
            labels[valid] = best_lab
    units = sorted(set(labels))

    lc = grid.values("lcdb_class", rows, cols)
    lc_names = json.loads((env_dir / "lcdb_classes.json").read_text(encoding="utf-8"))
    wst = grid.values("wetland_status", rows, cols)
    # Potential natural ecosystem (Eco-index Ecosystem Projector), if gridded:
    # context for each unit, not a model input.
    pot = pot_names = None
    if "potential_ecosystem" in grid.layers:
        pot = grid.values("potential_ecosystem", rows, cols)
        pot_names = json.loads(gridio.read_bytes(env_dir / "potential_ecosystem_classes.json"))

    # unit polygons for the map: each unit's cells merged, cut to the site
    boxes = grid.cell_boxes(rows, cols)
    feats = []
    for u in units:
        g = shapely.intersection(shapely.union_all(boxes[labels == u]), poly)
        if g.is_empty:
            continue
        g_ll = json.loads(shapely.to_geojson(nztm.geom_from_nztm(g)))
        feats.append({"type": "Feature", "properties": {"unit": int(u) + 1}, "geometry": g_ll})
    (out_dir / "units.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")

    # ── reference records ─────────────────────────────────────────────────
    # Read the bytes and check for gzip, since a web host may already have
    # unzipped the file in transit.
    raw = gridio.read_bytes(ROOT / "data" / f"records_{region}_tagged.csv.gz")
    rec = pd.read_csv(io.BytesIO(raw), compression="gzip" if raw[:2] == GZIP else None, low_memory=False)
    # Records inside the site itself are left out: they are often plantings,
    # and they would let the prediction just repeat what is already there.
    # 100 m buffer (one grid cell) catches on-site records with GPS scatter.
    rx, ry = nztm.to_nztm(rec["decimalLongitude"].to_numpy(), rec["decimalLatitude"].to_numpy())
    on_site = shapely.contains_xy(poly.buffer(ON_SITE_BUFFER_M), rx, ry)
    n_on_site = int(on_site.sum())
    rec = rec[~on_site].reset_index(drop=True)
    print(f"Left out {n_on_site} records inside the site")
    rec["stage"] = rec["lcdb_at_record"].map(stage_of)
    renv = transform_vals(rec[[f"env_{v}" for v in VARS]].set_axis(VARS, axis=1))
    rec_Z = ((renv - mu) / sd)[VARS].to_numpy()
    rec["name"] = rec["nztcs_name"].fillna(rec["species"]).map(clean_name)
    two = rec["name"].str.split().str[:2].str.join(" ")
    sp_level = set(rec.loc[rec["name"] == two, "name"])
    merge = (rec["name"] != two) & two.isin(sp_level)
    if merge.any():
        cat = rec[rec["name"] == two].drop_duplicates("name").set_index("name")
        rec.loc[merge, "name"] = two[merge]
        rec.loc[merge, "category"] = rec.loc[merge, "name"].map(cat["category"])
        rec.loc[merge, "bioStatus"] = rec.loc[merge, "name"].map(cat["bioStatus"])
    # Common names: Occurd's NZTCS file locally, or the slim copy bundled
    # for hosting (data/nztcs_names.json, made by scripts/build_space.py).
    names_path = ROOT / "data" / "nztcs_names.json"
    if not names_path.exists():
        names_path = ROOT.parent / "Occurd" / "nztcs.json"
    nztcs = json.loads(names_path.read_text(encoding="utf-8"))
    common = {}
    for v in nztcs.values():
        if isinstance(v, dict) and v.get("name"):
            cn = v.get("maori") or v.get("common")
            if cn:
                common.setdefault(clean_name(v["name"]), cn)
    # A species-level name NZTCS only lists by subspecies or variety takes the
    # nominate's common name (Piper excelsum -> kawakawa, from subsp. excelsum),
    # never another subspecies' (subsp. delangei is de Lange's kawakawa).
    for v in nztcs.values():
        if isinstance(v, dict) and v.get("name"):
            w = v["name"].split()
            cn = v.get("maori") or v.get("common")
            if cn and len(w) >= 4 and w[3] == w[1]:
                common.setdefault(" ".join(w[:2]), cn)

    def label(s):
        c = common.get(s)
        return f"{c} ({s})" if c else s

    nvs = rec[rec["source"] == "NVS"]
    visits = nvs.groupby("visit").agg(stage=("stage", "first"), idx=("stage", lambda s: s.index[0]),
                                      lat=("decimalLatitude", "first"), lon=("decimalLongitude", "first"),
                                      year=("year", "first"))
    visit_Z = rec_Z[visits["idx"].to_numpy()]
    visit_species = nvs.groupby("visit")["name"].agg(set)
    gf = load_growth_forms()
    visits["stage"], n_restaged = restage_plots(visits["stage"], visit_species, gf)
    print(f"Re-staged {n_restaged} NVS plots from what they recorded (LCDB said open or excluded cover)")
    # typical NN spread among plots, to judge how close a unit's analogues are
    obs = rec[rec["source"] != "NVS"].copy()
    # Open-ground observations: drop those at a bush edge (likely in an
    # unmapped remnant) and forest-only plants (a lone record of a forest fern
    # in "pasture" says nothing about what colonises open ground).
    is_open = obs["stage"] == OPEN
    edge = is_open & (obs["dist_woody_m"] <= EDGE_M)
    habitat = obs["name"].map(lambda s: (gf(s) or (None, None))[1])
    forest_only = is_open & ~edge & (habitat == "forest")
    obs.loc[edge | forest_only, "stage"] = None
    print(f"Open-ground observations: {int(edge.sum())} at a bush edge and {int(forest_only.sum())} "
          f"forest-only plants set aside; {int((obs['stage'] == OPEN).sum())} kept")
    no_form = sorted({s for s in rec["name"] if gf(s) is None})
    if no_form:
        print(f"No growth form for {len(no_form)} names: {', '.join(no_form[:10])}")
    nat_wl = rec["gdc_wl_status"].isin(NATURAL_WETLAND)

    units_meta, stages_meta = [], []
    rows_out, report = [], [f"# Rightree prediction: {site}", "",
                            f"Region data: {region}. Natives only. Plots: NVS via GBIF; "
                            f"observations: iNaturalist and herbaria. {n_on_site} records in or within "
                            f"{ON_SITE_BUFFER_M} m of the site were left out, so existing plantings don't drive the list.", ""]
    for u in units:
        m = labels == u
        zc = np.nanmedian(Z[m], axis=0)
        e = cells[m].median()
        covers = pd.Series(lc[m]).map(lambda v: lc_names.get(str(v), "no data")).value_counts()
        has_wl = bool(np.isin(wst[m], [1, 2, 3]).any())
        potential = []
        if pot is not None:
            pc = pd.Series(pot[m]).value_counts()
            potential = [{"name": pot_names[str(k)]["name"], "group": pot_names[str(k)]["group"],
                          "share": round(v / m.sum(), 2)}
                         for k, v in pc.items() if k > 0 and v / m.sum() >= 0.05][:4]
        report += [f"## Unit {u + 1}: {m.sum() * 1:,} ha",
                   f"- Mean annual temp {e['temp_meanAnn']:.1f} °C, rainfall {e['precip_ann']:.0f} mm, "
                   f"slope {e['slope_deg']:.0f}°, {np.expm1(e['distance_coast']) / 1000:.1f} km from coast",
                   "- Land cover now: " + ", ".join(f"{k} {v / m.sum():.0%}" for k, v in covers.head(4).items()),
                   f"- Natural wetland in unit: {'yes' if has_wl else 'no'}"]
        if potential:
            report.append("- Potential natural ecosystem (Eco-index): "
                          + ", ".join(f"{p['name']} {p['share']:.0%}" for p in potential))
        report.append("")
        units_meta.append({"unit": u + 1, "ha": int(m.sum()), "temp": round(float(e["temp_meanAnn"]), 1),
                           "rain": round(float(e["precip_ann"])), "slope": round(float(e["slope_deg"])),
                           "coast_km": round(float(np.expm1(e["distance_coast"])) / 1000, 1),
                           "covers": {k: round(v / m.sum(), 2) for k, v in covers.head(4).items()},
                           "wetland": has_wl, "potential": potential,
                           "attrs": {v: (None if not np.isfinite(e[v]) else
                                         round(float(np.expm1(e[v]) if v in ("distance_coast", WATER) else e[v]), 2))
                                     for v in VARS},
                           "scaled": {v: (None if not np.isfinite(zc[i]) else round(float(zc[i]), 3))
                                      for i, v in enumerate(VARS)}})
        for stage in STAGES:
            sel = (visits["stage"] == stage).to_numpy()
            d = dist(zc, visit_Z[sel])
            osel = (obs["stage"] == stage).to_numpy()
            od = dist(zc, rec_Z[obs.index[osel]])

            # Tier 1: close analogues. Tier 2 (fallback): best available within
            # FALLBACK_D that still pass the veto, flagged in the report.
            tier = "close"
            pi, oi = within(d, MAX_D, K_PLOTS), within(od, MAX_D, K_OBS)
            if len(pi) < MIN_PLOTS and len(oi) < MIN_OBS:
                tier = "best available"
                pi, oi = within(d, FALLBACK_D, K_PLOTS), within(od, FALLBACK_D, K_OBS)
            limit = MAX_D if tier == "close" else FALLBACK_D
            min_p = MIN_PLOTS if tier == "close" else MIN_PLOTS_FB
            min_o = MIN_OBS if tier == "close" else MIN_OBS_FB
            near = visits.index[sel][pi]
            n_plots = len(near)
            freq = (pd.Series([s for v in near for s in visit_species[v]], dtype=object).value_counts() / n_plots
                    if n_plots >= min_p else pd.Series(dtype=float))
            onear = obs[osel].iloc[oi]
            oshare = onear["name"].value_counts() / max(len(onear), 1)

            fin = d[np.isfinite(d)]
            nearest = float(fin.min()) if len(fin) else np.nan
            near_txt = f"nearest {nearest:.2f}" if np.isfinite(nearest) else "none pass the climate/coast veto"
            report.append(f"### {stage}" + (" (best available, not close matches)" if tier != "close" else ""))
            meta = {"unit": u + 1, "stage": stage, "tier": tier, "limit": limit, "n_plots": int(n_plots),
                    "n_obs": int(len(onear)), "nearest": None if not np.isfinite(nearest) else round(nearest, 3),
                    "enough": True, "obs_only": False, "plots_used": []}
            stages_meta.append(meta)
            report.append(f"- Evidence: {n_plots} NVS plots within distance {limit} "
                          f"({near_txt}); {len(onear)} observations within {limit}")
            if n_plots < min_p and len(onear) < min_o:
                report += ["- **Not enough similar sites for a list, even allowing weaker matches.**", ""]
                meta["enough"] = False
                continue
            if tier != "close":
                report.append(f"- **No close matches (within {MAX_D}).** These are the nearest sites that "
                              f"still pass the climate/coast veto, up to {FALLBACK_D}. Treat as a lead to "
                              "check, not a prediction.")
                if n_plots:
                    pl = visits.loc[near].assign(d=d[pi]).drop_duplicates(["lat", "lon"]).head(5)
                    meta["plots_used"] = [{"lat": r.lat, "lon": r.lon, "year": int(r.year) if pd.notna(r.year) else None,
                                           "d": round(r.d, 3)} for r in pl.itertuples()]
                    report.append("- Plots used: " + "; ".join(
                        f"{r.lat:.4f}, {r.lon:.4f} ({int(r.year) if pd.notna(r.year) else '?'}, distance {r.d:.2f})"
                        for r in pl.itertuples()))
            if n_plots < min_p:
                meta["obs_only"] = True
                report.append(f"- Fewer than {min_p} plots: list from observations only, "
                              "so it shows what people have recorded, not what is absent.")
            spp = sorted(set(freq.index) | set(oshare.index))
            tab = pd.DataFrame({"plot_freq": freq.reindex(spp), "obs_share": oshare.reindex(spp)}).fillna(0)
            tab["score"] = tab["plot_freq"] + 0.5 * tab["obs_share"]
            tab = tab.sort_values("score", ascending=False)
            report.append("- Most expected: " + ", ".join(
                f"{label(s)} {r.plot_freq:.0%} of plots" if r.plot_freq > 0 else f"{label(s)} {r.obs_share:.0%} of obs"
                for s, r in tab.head(25).iterrows()))
            report.append("")
            for s, r in tab.iterrows():
                rows_out.append({"unit": u + 1, "stage": stage, "tier": tier, "species": s,
                                 "common_name": common.get(s), "plot_freq": round(r.plot_freq, 3),
                                 "n_plots": n_plots, "obs_share": round(r.obs_share, 3), "n_obs": len(onear),
                                 "nearest_plot_distance": round(nearest, 3)})

        if has_wl:
            wsel = nat_wl.to_numpy()
            wd = dist(zc, rec_Z[rec.index[wsel]])
            tier = "close"
            wi = within(wd, MAX_D, K_OBS)
            if len(wi) < 10:
                tier, wi = "best available", within(wd, FALLBACK_D, K_OBS)
            wnear = rec[wsel].iloc[wi]
            limit = MAX_D if tier == "close" else FALLBACK_D
            stages_meta.append({"unit": u + 1, "stage": "Wetland", "tier": tier, "limit": limit, "n_plots": 0,
                                "n_obs": int(len(wnear)), "nearest": None, "enough": len(wnear) >= 10,
                                "obs_only": True, "plots_used": []})
            report += ["### Wetland (records inside natural GDC wetlands at similar sites)"
                       + (" (best available, not close matches)" if tier != "close" else ""),
                       f"- Evidence: {len(wnear)} records within distance {limit}"]
            if len(wnear) >= 10:
                if tier != "close":
                    report.append(f"- **No close matches (within {MAX_D}).** Nearest natural-wetland records "
                                  f"up to {FALLBACK_D}; treat as a lead to check.")
                wshare = wnear["name"].value_counts() / len(wnear)
                report.append("- Most recorded: " + ", ".join(f"{label(s)} {v:.0%}" for s, v in wshare.head(20).items()))
                for s, v in wshare.items():
                    rows_out.append({"unit": u + 1, "stage": "Wetland", "tier": tier, "species": s,
                                     "common_name": common.get(s), "plot_freq": 0, "n_plots": 0,
                                     "obs_share": round(v, 3), "n_obs": len(wnear), "nearest_plot_distance": np.nan})
            else:
                report.append("- **Not enough similar wetland records for a list, even allowing weaker matches.**")
            report.append("")

    sp = pd.DataFrame(rows_out)
    if len(sp):
        status = rec.drop_duplicates("name").set_index("name")[["category", "bioStatus"]]
        sp = sp.join(status, on="species")
        layers = load_layers()
        sp["growth_form"] = sp["species"].map(lambda s: (gf(s) or (None,))[0])
        sp["layers"] = sp["species"].map(lambda s: ";".join(layers(s)))
    sp.to_csv(out_dir / "species.csv", index=False)
    report += ["## Notes",
               "- Plot share: proportion of the most similar NVS plots, in that stage, that recorded the species. "
               "Plots list every species present, so this is the strongest evidence.",
               "- Observation share: proportion of the most similar iNaturalist/herbarium records. "
               "Presence-only and biased towards conspicuous species.",
               f"- Distance is Gower: the average gap per layer as a share of that layer's range across the region, "
               f"with climate, terrain and soil weighted equally. Only sites within {MAX_D} are used, and a site "
               f"is rejected if mean temperature, cold-month minimum, rainfall or distance to coast differs by "
               f"more than {VETO:.0%} of the regional range.",
               "- Most NVS plots date from the 1950s-60s and lie in the western ranges.",
               "- A starting list to check on the ground, not a survey."]
    (out_dir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    sp_json = json.loads(sp.to_json(orient="records")) if len(sp) else []
    (out_dir / "report.json").write_text(json.dumps({
        "site": site, "region": region, "n_on_site": n_on_site, "on_site_buffer_m": ON_SITE_BUFFER_M,
        "max_d": MAX_D, "fallback_d": FALLBACK_D, "groups": GROUPS, "wetland_var": WATER, "units": units_meta, "stages": stages_meta,
        "species": sp_json}, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
        encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
