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
    python scripts/predict.py tairawhiti <site-name> <polygon.geojson | WKT in lon/lat>
Writes data/predictions/<site-name>/: report.md, species.csv, units.geojson
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import shapely
from rasterio.features import rasterize, shapes
from rasterio.warp import transform_geom
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

ROOT = Path(__file__).resolve().parent.parent

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


def read_polygon(arg):
    p = Path(arg)
    if p.exists():
        gj = json.loads(p.read_text(encoding="utf-8"))
        geoms = [f["geometry"] for f in gj["features"]] if gj.get("type") == "FeatureCollection" else [gj.get("geometry", gj)]
        return shapely.union_all([shapely.from_geojson(json.dumps(g)) for g in geoms])
    return shapely.from_wkt(arg)


def env_stack(env_dir, rows, cols):
    """Values of every VAR at the given cells."""
    out = {}
    for v in VARS:
        with rasterio.open(env_dir / f"{v}.tif") as s:
            a = s.read(1).astype("float64")
            if s.nodata is not None:
                a[a == s.nodata] = np.nan
        out[v] = a[rows, cols]
    return transform_vals(pd.DataFrame(out))


def region_stats(env_dir, inside, n=200_000, seed=1):
    rng = np.random.default_rng(seed)
    r, c = np.nonzero(inside)
    pick = rng.choice(len(r), size=min(n, len(r)), replace=False)
    sample = env_stack(env_dir, r[pick], c[pick])
    # Gower-style scaling: each layer by its range across the region
    # (1st-99th percentile, so a few extreme cells don't set the scale).
    lo, hi = sample.quantile(0.01), sample.quantile(0.99)
    return lo, (hi - lo).replace(0, 1)


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


def main():
    region, site, poly_arg = sys.argv[1], sys.argv[2], sys.argv[3]
    env_dir = ROOT / "data" / "env" / region
    out_dir = ROOT / "data" / "predictions" / site
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── cells of the polygon ──────────────────────────────────────────────
    poly_ll = read_polygon(poly_arg)
    with rasterio.open(env_dir / "elevation.tif") as ref:
        transform, shape, crs = ref.transform, ref.shape, ref.crs
        elev = ref.read(1)
    poly = shapely.from_geojson(json.dumps(transform_geom("EPSG:4326", crs, json.loads(shapely.to_geojson(poly_ll)))))
    mask = rasterize([(json.loads(shapely.to_geojson(poly)), 1)], out_shape=shape, transform=transform,
                     fill=0, all_touched=False, dtype="uint8").astype(bool)
    if mask.sum() == 0:  # tiny polygon: take the cell under its centre
        c = poly.centroid
        rr, cc = rasterio.transform.rowcol(transform, c.x, c.y)
        mask[rr, cc] = True
    rows, cols = np.nonzero(mask)
    cells = env_stack(env_dir, rows, cols)
    land = cells[KEY_VARS].notna().all(axis=1).to_numpy()    # drop sea and no-data cells
    if not land.any():
        sys.exit("The polygon has no land cells with environmental data.")
    if (~land).any():
        print(f"Dropped {int((~land).sum())} cells with no environmental data (sea or outside the layers).")
    rows, cols, cells = rows[land], cols[land], cells[land].reset_index(drop=True)
    mask = np.zeros_like(mask)
    mask[rows, cols] = True
    region_geo = json.loads((env_dir / "region_osm_nominatim.json").read_text())[0]["geojson"]
    inside = rasterize([(transform_geom("EPSG:4326", crs, region_geo), 1)], out_shape=shape,
                       transform=transform, fill=0, dtype="uint8").astype(bool) & np.isfinite(elev)
    mu, sd = region_stats(env_dir, inside)
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
            if s > best_s:
                best_k, best_s, best_lab = k, s, lab
        if best_k > 1:
            labels[valid] = best_lab
    units = sorted(set(labels))

    with rasterio.open(env_dir / "lcdb_class.tif") as s:
        lc = s.read(1)[rows, cols]
    lc_names = json.loads((env_dir / "lcdb_classes.json").read_text(encoding="utf-8"))
    with rasterio.open(env_dir / "wetland_status.tif") as s:
        wst = s.read(1)[rows, cols]

    # unit polygons for the map
    lab_grid = np.full(shape, 255, dtype="uint8")
    lab_grid[rows, cols] = labels
    feats = []
    for geom, val in shapes(lab_grid, mask=lab_grid != 255, transform=transform):
        g = shapely.intersection(shapely.from_geojson(json.dumps(geom)), poly)
        g_ll = transform_geom(crs, "EPSG:4326", json.loads(shapely.to_geojson(g)))
        feats.append({"type": "Feature", "properties": {"unit": int(val) + 1}, "geometry": g_ll})
    (out_dir / "units.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")

    # ── reference records ─────────────────────────────────────────────────
    rec = pd.read_csv(ROOT / "data" / f"records_{region}_tagged.csv.gz", low_memory=False)
    rec["stage"] = rec["lcdb_at_record"].map(stage_of)
    renv = transform_vals(rec[[f"env_{v}" for v in VARS]].set_axis(VARS, axis=1))
    rec_Z = ((renv - mu) / sd)[VARS].to_numpy()
    rec["name"] = rec["nztcs_name"].fillna(rec["species"]).map(clean_name)
    nztcs = json.loads((ROOT.parent / "Occurd" / "nztcs.json").read_text(encoding="utf-8"))
    common = {}
    for v in nztcs.values():
        if isinstance(v, dict) and v.get("name"):
            cn = v.get("maori") or v.get("common")
            if cn:
                common.setdefault(clean_name(v["name"]), cn)

    def label(s):
        c = common.get(s) or common.get(" ".join(s.split()[:2]))
        return f"{c} ({s})" if c else s

    nvs = rec[rec["source"] == "NVS"]
    visits = nvs.groupby("visit").agg(stage=("stage", "first"), idx=("stage", lambda s: s.index[0]))
    visit_Z = rec_Z[visits["idx"].to_numpy()]
    visit_species = nvs.groupby("visit")["name"].agg(set)
    # typical NN spread among plots, to judge how close a unit's analogues are
    obs = rec[rec["source"] != "NVS"]
    nat_wl = rec["gdc_wl_status"].isin(NATURAL_WETLAND)

    rows_out, report = [], [f"# Rightree prediction: {site}", "",
                            f"Region data: {region}. Natives only. Plots: NVS via GBIF; "
                            f"observations: iNaturalist and herbaria.", ""]
    for u in units:
        m = labels == u
        zc = np.nanmedian(Z[m], axis=0)
        e = cells[m].median()
        covers = pd.Series(lc[m]).map(lambda v: lc_names.get(str(v), "no data")).value_counts()
        has_wl = bool(np.isin(wst[m], [1, 2, 3]).any())
        report += [f"## Unit {u + 1}: {m.sum() * 1:,} ha",
                   f"- Mean annual temp {e['temp_meanAnn']:.1f} °C, rainfall {e['precip_ann']:.0f} mm, "
                   f"slope {e['slope_deg']:.0f}°, {np.expm1(e['distance_coast']) / 1000:.1f} km from coast",
                   "- Land cover now: " + ", ".join(f"{k} {v / m.sum():.0%}" for k, v in covers.head(4).items()),
                   f"- Natural wetland in unit: {'yes' if has_wl else 'no'}", ""]
        for stage in STAGES:
            sel = (visits["stage"] == stage).to_numpy()
            d = dist(zc, visit_Z[sel])
            order = np.argsort(d)
            close = order[d[order] <= MAX_D][:K_PLOTS]
            near = visits.index[sel][close]
            n_plots = len(near)
            freq = (pd.Series([s for v in near for s in visit_species[v]], dtype=object).value_counts() / n_plots
                    if n_plots >= MIN_PLOTS else pd.Series(dtype=float))

            osel = (obs["stage"] == stage).to_numpy()
            od = dist(zc, rec_Z[obs.index[osel]])
            oorder = np.argsort(od)
            oclose = oorder[od[oorder] <= MAX_D][:K_OBS]
            onear = obs[osel].iloc[oclose]
            oshare = onear["name"].value_counts() / max(len(onear), 1)

            fin = d[np.isfinite(d)]
            nearest = float(fin.min()) if len(fin) else np.nan
            report.append(f"### {stage}")
            near_txt = f"nearest {nearest:.2f}" if np.isfinite(nearest) else "none pass the climate/coast veto"
            report.append(f"- Evidence: {n_plots} NVS plots within distance {MAX_D} "
                          f"({near_txt}); {len(onear)} observations within {MAX_D}")
            if n_plots < MIN_PLOTS and len(onear) < 20:
                report += ["- **Not enough similar sites for a list.**", ""]
                continue
            if n_plots < MIN_PLOTS:
                report.append(f"- Fewer than {MIN_PLOTS} close plots: list from observations only, "
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
                rows_out.append({"unit": u + 1, "stage": stage, "species": s, "common_name": common.get(s),
                                 "plot_freq": round(r.plot_freq, 3), "n_plots": n_plots,
                                 "obs_share": round(r.obs_share, 3), "n_obs": len(onear),
                                 "nearest_plot_distance": round(nearest, 3)})

        if has_wl:
            wsel = nat_wl.to_numpy()
            wd = dist(zc, rec_Z[rec.index[wsel]])
            worder = np.argsort(wd)
            wnear = rec[wsel].iloc[worder[wd[worder] <= MAX_D][:K_OBS]]
            report += ["### Wetland (records inside natural GDC wetlands at similar sites)",
                       f"- Evidence: {len(wnear)} records within distance {MAX_D}"]
            if len(wnear) >= 10:
                wshare = wnear["name"].value_counts() / len(wnear)
                report.append("- Most recorded: " + ", ".join(f"{label(s)} {v:.0%}" for s, v in wshare.head(20).items()))
                for s, v in wshare.items():
                    rows_out.append({"unit": u + 1, "stage": "Wetland", "species": s, "common_name": common.get(s),
                                     "plot_freq": 0, "n_plots": 0, "obs_share": round(v, 3), "n_obs": len(wnear),
                                     "nearest_plot_distance": np.nan})
            else:
                report.append("- **Not enough similar wetland records for a list.**")
            report.append("")

    sp = pd.DataFrame(rows_out)
    if len(sp):
        status = rec.drop_duplicates("name").set_index("name")[["category", "bioStatus"]]
        sp = sp.join(status, on="species")
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
    print("\n".join(report))


if __name__ == "__main__":
    main()
