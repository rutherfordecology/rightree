# Rightree design notes

## The question

Given a polygon, which native plant species are expected there, and which
would establish at each successional stage?

## Method: environmental analogue

This is species distribution modelling of the simplest, most explainable kind:

- Describe every grid cell (about 100 m) by its environment.
- Attach occurrence records to the cells they fall in.
- For a query unit, find the most environmentally similar cells (Gower
  distance over mixed numeric and categorical variables). Only search within
  the same or neighbouring Ecological Districts.
- Report each species' frequency across those similar cells, and link to the
  records behind it.

Per-species models (MaxEnt and similar) can come later if the analogue
approach proves too noisy. The analogue approach is easier to explain to a
landowner: "this species was recorded in 62% of sites like yours".

## Data layers

| Factor | Source | Notes |
|---|---|---|
| Land environments | LENZ (Manaaki Whenua, LRIS) | Ready-made classification; also supplies about 15 underlying environmental layers |
| Soils | S-map, with Fundamental Soil Layers where S-map has gaps | Check licence |
| Geology | QMAP 1:250k (GNS) | |
| Slope, aspect | LINZ 8 m DEM | Derive locally |
| Climate | LENZ climate surfaces, or NIWA VCSN (licensed), or WorldClim/CHELSA as open fallback | |
| Land cover | LCDB v5/v6 | Successional stage of the record site |
| Biogeography | Ecological Regions and Districts | Constrains the search |
| Native status | NZPCN / NZOR | Filter natives; flag expected weeds separately |

Each layer's licence needs checking before anything is published.

**In use (v0.2.0): NZEnvDS v1.1** (McCarthy et al. 2021, doi:10.20417/nzjecol.45.31;
data doi:10.7931/m6rm-vz40; CC BY 4.0). It has 72 national layers at 100 m in
NZTM. We take 23:
- climate: mean annual temperature, minimum temperature of the coldest month,
  GDD5, annual rainfall, annual water deficit, October VPD, solar radiation,
  wind
- terrain: elevation, slope, northness, eastness, wetness, topographic
  position, distance to coast
- soil: the 8 Fundamental Soil Layers classes (drainage, pH, age, particle
  size, acid P, calcium, induration, chemical limitations)

NZEnvDS has no geology, so QMAP is still to add. The soil layers are ordinal
classes, not measurements, so treat them as ordinal in the distance measure.
Land cover (LCDB) is also still to add.

**Wetlands (v0.3.0): GDC Regional Wetland Assessment 2022 (Morphum)**, CC BY
4.0. This is a desktop assessment from aerial imagery and LiDAR, not
field-verified; each polygon has a confidence rating. Its description lists
six catchments (Waipaoa, Waiapu, Hangaroa-Ruakituri, Uawa, Waimata,
Wharekahika-Waikura), so the rest of the region may be unmapped rather than
dry. Check this before treating "no wetland" as an absence. It covers
Gisborne only, so a wider analogue pool will need another source outside the
region (for example the national wetland layers or LCDB's wetland classes).

**Land cover (v0.4.0): LCDB v6** from the LRIS WFS service (layer 123148,
CC BY 4.0, needs an LRIS key). Records get the cover at the LCDB date nearest
their year. Most NVS plots predate 1996, so for them this is the 1996 cover,
which assumes the site had not changed since the plot was measured.

In Gisborne, the succession split is thin outside forest. Indigenous forest
has 568 NVS visits and broadleaved hardwoods 42, but mānuka/kānuka has only 12
and pasture 8. Scrub and early-succession lists will lean on iNaturalist and
herbarium records, which have no absences, unless the area is widened.

## Occurrence data

- **GBIF:** presence-only. Filter to coordinate uncertainty of 100 m or
  better. It is biased towards roads, tracks and iNaturalist users, so the
  absence of a record is not evidence of absence.
- **NVS (National Vegetation Survey Databank):** precisely located plots, strong
  on forest. Much of it is already on GBIF as dataset
  `788439f0-3b56-11dc-8c19-b8a03c50a862` (doi:10.15468/uzxpbn): about 1.6
  million records, about 1.5 million of them within 100 m uncertainty, and
  about 48,000 in a Tairāwhiti bounding box (checked 2026-11-09). Each record
  carries an `eventID` (the plot visit), so a plot can be treated as a complete
  species list, which gives inferred absences. The licence is **CC BY-NC 4.0**,
  so commercial or consulting use needs the owners' permission through Manaaki
  Whenua. Restricted datasets not on GBIF need a request through
  nvs.landcareresearch.co.nz (register, add to Request Cart, owner approval).
- **Covenant species records are excluded.** They are private and must not be
  used for training, matching or output.

- **Cultivated records.** GBIF's simple CSV has no `establishmentMeans`, so
  planted collections get through. Known sites go in
  `config/cultivated_sites.json`. Planted natives in gardens and restoration
  plantings remain a source of noise.
- **Natives only (v0.5.0).** Native status comes from NZTCS through Occurd's
  but-is-it-threatened resolver, with NZOR synonyms and hand-checked
  overrides. It reads `../Occurd/nztcs.json` and
  `../Occurd/but-is-it-threatened/`, so Rightree expects the Occurd repo next
  to it. Unresolved names with few records still to check: Coprosma conferta,
  Hypolepis tenuifolia, Hymenophyllum rarum (see
  `data/native_status_<name>.csv`).

## Known pitfalls

1. **Biogeography.** Similar environment does not mean the same species (for
   example, kauri south of 38°S, or gaps in beech distribution). Handled by the
   Ecological District constraint.
2. **Sampling bias.** Common, easily seen species are over-recorded. Report
   frequencies relative to the sampling effort in similar cells.
3. **Coordinate precision.** Older herbarium records are often too vague to
   use.
4. **Current vs potential.** A record in pasture or in mānuka scrub tells you
   about that stage, not about the mature community. Split output by LCDB class.

## Output

For each unit:
- a ranked native species list with frequency and record count
- grouped by LCDB class (succession sequence)
- expected weeds flagged separately
- an export for `projects/<job>/data/` (CSV with a GBIF download DOI citation,
  plus units as GeoJSON/KML)

## Fallback and on-site records (v0.7.0)

Close analogues are within Gower 0.15. When a stage has none, the nearest sites up to 0.35 that pass the veto are used and flagged "best available". The cut-off is a judgement call: 0.35 still finds lowland alluvial forest plots for the flats, but on the user's orchard site by the Waipaoa it found only 1 forest plot. The flats have lost their native vegetation, so the region alone has too few analogues. The fix is a wider pool (Hawke's Bay, Bay of Plenty), not a looser threshold.

Records in or within 100 m of the site are dropped. On-site iNat records (cabbage tree, karo, wharangi, mānuka) were likely plantings, and 4 of them sat just outside the drawn line.

## Plan

1. **Prototype (Python notebook), one region:** build the grid, attach the
   layers and filtered GBIF records, run a test polygon, and check the list
   against a site known well.
2. If the lists look sensible: precompute per region and build a static web
   front end in the same style as Occurd and inferrd, reusing Occurd's polygon
   drawing.
3. Validate: hold out NVS plots or known sites, and compare against Leathwick's
   potential vegetation models.

## Open questions

- Which region to prototype? (Tairāwhiti suggested.)
- Can NVS access be obtained?
- Precompute offline and serve static tiles, or query Earth Engine (already
  set up for inferrd)? Most NZ layers (S-map, QMAP, LENZ) are not in Earth
  Engine, so offline precompute is the likely route.
