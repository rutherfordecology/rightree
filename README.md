# Rightree

Right tree, right place. Draw a boundary and get the native plant species that
are expected there, based on where those species have been recorded in
environmentally similar places nearby.

Rightree predicts plant communities, not just trees: shrubs, ferns, sedges and
herbs come out of the same analysis. The list is meant to inform management and
revegetation planning. It is a starting point to be checked on the ground, not
a survey.

Status: prototype (v0.17.1). First predictions run; native records are tagged with environment,
land cover and wetlands. See
[`docs/design.md`](docs/design.md).

## Building a region's data

1. **Occurrences.** In Occurd's Big Data Mode, draw the area, tick
   Angiosperms, Gymnosperms and Ferns & allies, clear the From date, and fetch.
   Save GBIF's zip, keeping its name (`<downloadkey>.zip`), in `data/`.
2. **Region boundary.** Save it as `data/env/<name>/region_osm_nominatim.json`
   (a Nominatim search result with `polygon_geojson=1`).
3. **LRIS key.** Put your LRIS API key in `.lris_key` (gitignored).
4. Run, with the region's lon/lat bounding box and a margin in km:

```bash
python scripts/load_gbif.py data/<downloadkey>.zip <name>
python scripts/native_status.py <name>      # review table of native verdicts
python scripts/summarise_gbif.py <name>
python scripts/fetch_env.py <name> <minlon,minlat,maxlon,maxlat> 50
python scripts/fetch_gdc_wetlands.py <name>
python scripts/fetch_lcdb.py <name> <minlon,minlat,maxlon,maxlat> 50
python scripts/tag_records.py <name>
```

`fetch_gdc_wetlands.py` is Gisborne-only. Native status needs Node and the
Occurd repo checked out next to this one (it uses Occurd's NZTCS and NZOR name
files and the but-is-it-threatened resolver).

## Predicting a site

### On a map

```bash
python scripts/serve.py
```

Builds the site into `site/` and serves it at http://127.0.0.1:7882. Draw the
site (same tools as Occurd), or load a KML exported from Occurd, and press
Predict. Distinct habitats are mapped as units, each with its model inputs
and what sets it apart. Lists show by unit and stage, with species linked to
LookLike. Download the species CSV, the units as GeoJSON, or a Word
plant checklist for the field.

The model runs in the browser (Pyodide, in a Web Worker), so the site is
plain files and needs no server. The grids are cut into 256-cell tiles
(`scripts/make_tiles.py`, rerun after the grids change) and a prediction
downloads only the tiles under the site. The first prediction after opening
the page also loads Python and its packages (about 30 MB, cached after).

### Publishing

```bash
python scripts/build_site.py <folder>
```

Writes the static site (about 48 MB, mostly tiles) to `<folder>`, keeping a
`.git` there. Commit and push the folder to the `gh-pages` branch to publish
on GitHub Pages. Visitors see a welcome note first; nothing large downloads
until they accept. Areas over 20,000 ha are refused.

### From the command line

```bash
python scripts/predict.py <region> <site-name> <area.kml | .kmz | .geojson | "POLYGON((lon lat, ...))">
```

Writes `report.md`, `report.json`, `species.csv` and `units.geojson` to
`data/predictions/<site-name>/`.

## How it works

1. **Units.** The polygon's 100 m cells are split into 1–4 units that differ
   in climate, terrain and soil. A split is kept only when it is clear, each
   unit is at least 10% of the site, and units are at least 0.05 apart. Sea
   and no-data cells are dropped.
2. **Similar sites.** Each unit is compared with every record's site using a
   Gower distance (climate, terrain and soil weighted equally). A site counts
   only if it is close overall and no more than a quarter of the regional range
   away in temperature, frost, rainfall or distance to the coast.
3. **Stages.** Similar sites are split by their land cover when recorded:
   mature forest; regenerating hardwoods, mānuka/kānuka and scrub; and open
   ground. That gives a succession sequence. NVS plots that LCDB maps as
   open but that recorded forest canopy or woody genera are moved to the
   forest stages, because LCDB misses small remnants. Open-ground
   observations within 50 m of bush, or of forest-only plants, are set aside.
   Growth forms and habitats are in `config/growth_forms.json`.
4. **Lists.** Plot share is the share of the closest NVS plots that recorded
   each species; plots list everything present, so this is the strongest
   evidence. Observation share is the same from iNaturalist and herbarium
   records, which are presence-only. A unit with a natural GDC wetland also
   gets a wetland list. Where evidence is too thin, the report says so.
5. **Fallback.** If a stage has no close sites, the report shows the nearest
   ones that still pass the veto (up to 0.35), headed "best available, not
   close matches", with where and when those plots were. Treat these as leads.
   Records in or within 100 m of the site are always left out, so existing
   plantings don't feed back into the list.

Still to come: geology (QMAP), Ecological District limits, and a wider
analogue pool beyond the region.

## Related tools

- **Occurd:** shows what *has been* recorded in an area. Rightree says what
  *should be* there.
- **inferrd:** tracks vegetation change over time from Sentinel-2.
- **Report workflow:** Rightree exports data into `projects/<job>/data/`. It
  does not write reports.
