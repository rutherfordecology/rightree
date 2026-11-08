# Changelog

## v0.15.0 (November 2026)

- **Runs in the browser.** Hugging Face now charges for Docker Spaces, so
  the model moved into the page: `scripts/predict.py` runs in Pyodide in a
  Web Worker (`web/worker.js`), and the site is plain files any static host
  can serve. Predictions match the server version exactly on all four test
  sites.
- **No rasterio in the model.** The grids are read from 256-cell tiles
  (`scripts/gridio.py`, made by `scripts/make_tiles.py`), so a prediction
  downloads only the tiles under the site. NZTM projection is done in numpy
  (`scripts/nztm.py`, matches PROJ to under a millimetre). Regional ranges
  are computed once and saved to `region_stats.json`.
- `scripts/build_site.py` builds the static site; `scripts/serve.py` now
  builds it and serves the files. The Docker files and `build_space.py`
  are gone.

## v0.14.0 (November 2026)

- **Hostable.** `scripts/build_space.py` builds a Hugging Face Space
  (Docker) with the app and only the data a prediction needs; the
  Dockerfile, requirements and Space README are in `space/`.
- **Server:** reads `HOST` and `PORT` from the environment; run ids carry a
  random suffix; keeps the latest 200 runs; limits uploads to 5 MB and a
  prediction to 5 minutes; the previous-runs list endpoint is gone.
- **Model:** areas over 20,000 ha are refused with a message. Common names
  come from a bundled `data/nztcs_names.json` when present, else Occurd's
  `nztcs.json`.
- **Map page:** a "Sources and credits" footer with the GBIF download
  citation and the licences of each dataset.

## v0.13.1 (November 2026)

- The map page opens on aerial imagery (Satellite) instead of the street map.

## v0.13.0 (November 2026)

- **Layers.** Each species gets the layers it can fill: canopy, subcanopy,
  understorey, ground cover, and climber or epiphyte. They come from its
  growth form (`layer_of_form` in `config/growth_forms.json`), with 31
  genus or species overrides where a plant commonly fills more than one.
  Kānuka, māhoe and karaka are canopy and subcanopy; tree ferns are
  subcanopy and understorey. `species.csv` gains `growth_form` and `layers`.
- **Map page:**
  - Species tables have a tick column for each layer.
  - Filter buttons (All layers, Canopy, Subcanopy, Understorey, Ground
    cover, Climbers & epiphytes) apply to every list. A filtered list shows
    every match, not just the top 25.
- **Likelihood.** Each species is marked:
  - **Expected:** in 40% or more of the similar plots (at least 2).
  - **Likely:** in 15% or more of the plots (at least 2), or 3 or more
    records.
  - **Possible:** a single plot, or one or two records.

  Possible species are hidden unless "Show possible" is ticked, which takes
  out the long tail of one-off species. Waimata's regenerating list drops
  from 48 to 17. The downloaded CSV includes likelihood, growth form and
  layers.
- The sidebar is wider (540 px) to fit the new columns.

## v0.12.2 (November 2026)

- Removed "(opens in LookLike)" from the species table heading.

## v0.12.1 (November 2026)

- The map page shows the version next to the title. `serve.py` reads it from
  the newest CHANGELOG entry (`/api/version`).

## v0.12.0 (November 2026)

- The map page lists the site area under the buttons, like Occurd's
  drawn-polygon list, with its name and size. The name updates as you type.
  Its ✕ deletes the area, its units and plot markers and the results, ready
  for the next site.

## v0.11.2 (November 2026)

- Fixed common names for species that NZTCS splits into subspecies. v0.11.0
  gave a species-level name the first common name found under it, so
  *Piper excelsum* showed as "de Lange's kawakawa" (subsp. *delangei*, At
  Risk). It now takes the nominate's name (kawakawa, from subsp.
  *excelsum*), or none. All 34 split species in the Gisborne data were
  checked.
- Report labels no longer borrow a species' common name for a different
  subspecies.

## v0.11.1 (November 2026)

- The map page no longer says how long a prediction takes.

## v0.11.0 (November 2026)

- **Subspecies matching fixed.** A species-level record was being assigned
  to the nominate subspecies or variety. In Gisborne, *Oplismenus hirtellus*
  became subsp. *hirtellus* (At Risk), though the common NZ plant is subsp.
  *imbecillis*. 34 species were affected, including *Solanum aviculare*,
  *Linum monogynum* and *Brachyglottis kirkii*, some with a wrong threat
  status.
  - Where NZTCS splits a species, a species-level record now stays at
    species level. It is native if any of its taxa is native, and it gets a
    threat category only if all its taxa share one.
  - Records identified to subspecies or variety are matched on that name,
    not the species.
  - In the lists, such records are merged into their species when that
    species also has species-level records, so a plant isn't listed twice.
  - Common names now also attach at species level.
- **Map page:**
  - Drawing works like Occurd: a polygon and rectangle toolbar; Finish,
    Undo point and Cancel buttons; segment lengths while drawing. A new area
    is orange and dashed while you adjust its corners, then solid.
  - Basemaps (Map, Satellite, Greyscale, Topo), fonts and square controls
    also follow Occurd.
  - Distinct habitats are mapped as coloured, labelled units. Each unit says
    what sets it apart from the others (inputs where it is above or below
    every other unit), and has a "Model inputs" table: all 20 inputs, for
    every unit side by side, grouped by climate, terrain, soil and wetland,
    with the separating rows shaded.
  - Species names open in LookLike, and each list has an "Open in LookLike"
    button.
  - The previous-runs list is gone. Downloads are a species CSV and the
    units as GeoJSON with their model inputs.
- `report.json` now carries each unit's model inputs (natural units and the
  0–1 regional scale) and the variable groups.

## v0.10.0 (November 2026)

- **Map interface.** `python scripts/serve.py` starts a local web page at
  http://127.0.0.1:7882. Draw a site on the map, or load a KML, KMZ or
  GeoJSON (e.g. exported from Occurd), and press Predict (about 10
  seconds). The page shows:
  - each unit on the map, with its climate, slope, distance to the coast and
    current land cover;
  - a tab for each stage (mature forest, regenerating, open ground, wetland),
    marked green for close matches, amber for best available and grey for not
    enough evidence;
  - species tables with common and scientific names, % of plots (or of
    records), and NZTCS threat status for threatened species;
  - the NVS plots used for best-available lists, as markers on the map.
  It also lists previous runs and downloads the species list as CSV.
- The server binds to 127.0.0.1 only. The records include NVS plots under
  CC BY-NC, so the page is for local use, not publishing.
- `predict.py` also writes `report.json` (units, per-stage evidence and
  species) for the page.

## v0.9.0 (November 2026)

- **Growth-form table.** `config/growth_forms.json` gives every native genus
  in the Gisborne records (226) a growth form and usual habitat, set by hand.
  Forms are canopy tree, small tree, shrub, tree fern, fern, graminoid, herb,
  climber, epiphyte or aquatic. Habitat is forest, both, open, wetland or
  coast. About 30 species entries override their genus, e.g. forest vs
  pioneer Coprosma, and pōhutukawa as coastal. NZTCS has no growth form,
  so this replaces the genus lists in `config/plot_stage_indicators.json`
  (removed) for re-staging NVS plots. The same 16 plots move.
- **Cleaner Open lists.** Observations that LCDB maps as open ground are set
  aside if:
  - they are within 50 m of bush or scrub (likely in a remnant LCDB didn't
    map); or
  - the plant is forest-only (forest ferns, epiphytes, canopy trees).

  In Gisborne that sets aside 155 edge records and 59 forest-only records,
  leaving 201. Open lists are now what colonises open ground. The coast test
  gives mānuka, pōhuehue, koromiko, pōhutukawa, ake, tī kōuka, oioi and
  tātaraheke. Inland, the Open list is now usually "not enough evidence",
  which is honest: few people record natives in pasture.
- `tag_records.py` adds `dist_woody_m`: distance (up to 200 m) from each
  record to native forest, scrub, gorse or broom in LCDB at the record's
  date.

## v0.8.0 (November 2026)

- **NVS plots are staged by what they recorded**, not only by LCDB. LCDB maps
  down to about 1 ha, so a plot in a small forest remnant can sit in a
  polygon mapped as pasture. That put forest plots (kahikatea, kohekohe,
  tōtara) into the "Open" lists. A plot LCDB calls open, or an excluded cover,
  is now treated as:
  - mature forest if it records 3 or more forest canopy genera;
  - regenerating if it records 4 or more woody genera.
  The genus lists are in `config/plot_stage_indicators.json`. In Gisborne 16
  plots moved.
- **Units split only when the difference matters.** Each unit must hold at
  least 10% of the cells, and every pair of units must be at least 0.05 apart
  in Gower distance (a third of the analogue threshold). Otherwise the site
  stays whole. A 1 km square of Waimata valley pasture had been cut into 4
  near-identical units; it is now one. The flats test is now one unit
  (closest split 0.045 apart). The coast test drops a 5% sliver. The ranges
  still split into 3 (0.11 apart).
- `predict.py` prints the silhouette, smallest unit and gap for each split it
  tries.
- Known gap: "Open" lists built from observations still include woody
  species, because iNaturalist records in small remnants are mapped as
  pasture. They are flagged as observation-only.

## v0.7.0 (November 2026)

- **Best-available fallback.** If a stage has fewer than 5 close plots
  (within 0.15) and fewer than 20 close observations, `predict.py` falls back
  to the nearest sites up to 0.35 that still pass the climate/coast veto. It
  then needs at least 3 plots or 10 observations. The heading reads "best
  available, not close matches", and the report lists the plots used with
  location, year and distance. `species.csv` has a new `tier` column
  (`close` / `best available`). The wetland list falls back the same way.
- **On-site records left out.** Records in the site, or within 100 m of it,
  are dropped from the evidence. They are often plantings, and keeping them
  would make the prediction repeat what is already there. The report gives
  the count.
- `config/test_sites.json` holds the check polygons (flats, ranges, coast).
  Close-match lists for the flats and ranges are unchanged.
- Test on a real site (an orchard on young alluvium near the Waipaoa, 1.5 km
  from the coast): still no forest or scrub list, even at 0.35. Only a
  saltmarsh-leaning wetland lead. The Gisborne flats have almost no native
  analogues left on similar soils, so this needs a wider analogue pool.

## v0.6.1 (November 2026)

- `predict.py` reads KML and KMZ as well as GeoJSON and WKT, so an area drawn
  in Occurd and exported with its KML button can be used directly. Several
  polygons are merged, and holes are kept.

## v0.6.0 (November 2026)

- First predictions. `scripts/predict.py <region> <site> <polygon>` splits
  the polygon into 1–4 environmental units (k-means, only when the split is
  clear). For each unit and each successional stage (mature forest;
  regenerating hardwoods, mānuka/kānuka and scrub; open ground) it lists the
  native species of the most similar sites:
  - **Plot share:** the share of the closest NVS plots (up to 20) that recorded
    the species. Plots list everything present, so this is the strongest
    evidence.
  - **Observation share:** the share of the closest iNaturalist and herbarium
    records. Presence-only, so supporting evidence.
  - **Wetland list:** from records inside natural GDC wetlands, when the unit
    has one.
  Writes `report.md`, `species.csv` (with NZTCS status and common names) and
  `units.geojson` to `data/predictions/<site>/`.
- Similarity is a Gower distance: each layer scaled by its regional range,
  with climate, terrain and soil groups weighted equally. Sites must be within
  0.15. A site is vetoed if temperature, cold-month minimum, rainfall or
  distance to coast differs by more than a quarter of the range. This stopped
  dune plants being predicted 50 km inland. With too little evidence the
  report says so instead of giving a list.
- Soil class 0 is treated as no data. `soil_chemLims` is dropped (99.4% one
  class in Gisborne). Records in a no-data cell now take the nearest land
  cell within 300 m, so coastal records keep their environment.
- Tests: Poverty Bay flats → kahikatea, pukatea, pūriri, tawa, tītoki
  (lowland alluvial forest); western ranges → red and silver beech, rimu,
  tāwari, miro.

## v0.5.0 (November 2026)

- Natives only. `scripts/native_status.py` decides native status for each
  species. `scripts/resolve_names.mjs` resolves names with Occurd's
  but-is-it-threatened resolver (NZOR synonyms first, then NZTCS exact,
  prefix, nominate, typo and gender passes), and native means NZTCS
  bioStatus Endemic or Non-endemic. Names NZTCS lacks count as exotic.
- `config/native_overrides.json` fixes 16 natives the matcher missed, mostly
  recent GBIF genus transfers NZTCS hasn't adopted (Shawia → Olearia,
  Notelaea → Nestegis, Paratrophis microphylla → Streblus heterophyllus) and
  lumps (Quintinia acutifolia → Q. serrata, Nertera granadensis → N. depressa).
- `load_gbif.py` keeps natives in `records_<name>.csv.gz` and writes exotics
  to `records_<name>_exotic.csv.gz`, for weed flags later. Records now carry
  the NZTCS name, bioStatus and category. Gisborne: 14,334 native records of
  448 species; 790 exotic records of 366 species set aside.

## v0.4.0 (November 2026)

- Land cover: `scripts/fetch_lcdb.py` pulls LCDB v6 (1996–2023) polygons
  from the LRIS WFS service and puts 2023 cover on the 100 m grid. The LRIS
  key is read from `.lris_key` (gitignored) or `LRIS_KEY`. Gisborne plus
  50 km: 50,051 polygons, 31 classes.
- `scripts/tag_records.py` gives every record its land cover, using the
  exact LCDB polygon and the mapping date nearest the record's year (1996 for
  older records). It also adds the GDC wetland polygon it falls in and the
  value of every environmental layer at its cell.
- Cultivated sites: `config/cultivated_sites.json` lists planted collections
  whose records are dropped on load. It starts with Eastwoodhill Arboretum,
  where 870 records (mostly Auckland Museum specimens of planted oaks and
  maples) had shown up as a "Deciduous Hardwoods" cluster with 568 species.
  Gisborne now keeps 15,124 records of 814 species.

## v0.3.0 (November 2026)

- Wetlands from Gisborne District Council's Regional Wetland Assessment 2022
  (Morphum; CC BY 4.0): 3,542 polygons, classified by NPS-FM and Johnson &
  Gerbeaux wetland types. `scripts/fetch_gdc_wetlands.py` keeps the polygons
  and adds three grid layers: wetland class, wetland status (natural,
  induced, pasture, artificial) and distance to the nearest natural wetland.
  Cells outside the region are no data, because GDC only maps its own region.
- First check: 571 records (318 species) fall in wetland cells, including
  kahikatea, saltmarsh ribbonwood and cabbage tree. A 100 m cell that only
  touches a wetland edge also counts, so record tagging should use the
  polygons.

## v0.2.0 (November 2026)

- Environmental layers. `scripts/fetch_env.py` pulls 23 NZEnvDS v1.1 layers
  (climate, terrain and Fundamental Soil Layers; NZTM, 100 m, CC BY 4.0) out of
  the 4.4 GB national zip with range requests. It clips each layer to the
  region plus a margin and deletes the national copy straight away. Gisborne
  plus 50 km comes to 68 MB.
- `scripts/remote_zip.py` lists or extracts members of a large remote zip
  without downloading it all.

## v0.1.0 (November 2026)

- First data in. `scripts/load_gbif.py` reads a GBIF download zip from Occurd's
  Big Data Mode, keeps vascular plant records identified to species and located
  within 100 m, and drops Pl@ntNet automatic IDs. NVS plot visits are rebuilt
  from dataset, location and date, because GBIF's simple CSV has no plot ID. It
  writes the download's DOI and citation alongside the records.
- `scripts/summarise_gbif.py` reports sources, plot visits, years and the most
  widespread species, and draws a map of record locations.
- Gisborne Region test download: 28,439 records (doi:10.15468/dl.x7fpqf), of
  which 15,994 are kept. 639 NVS plot visits, mostly 1950s and 1960s, all in
  the western ranges.
- Removed the search-API fetch script: too slow, and its output has no DOI.

## v0.0.2 (November 2026)

- Design notes: most NVS plot data is already on GBIF (CC BY-NC 4.0) with plot
  IDs, so it can be used straight away for non-commercial prototyping.

## v0.0.1 (November 2026)

- Project started: name, concept, README and design notes. Nothing runs yet.
