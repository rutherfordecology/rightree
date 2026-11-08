# Changelog

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
