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

## Occurrence data

- **GBIF:** presence-only. Filter to coordinate uncertainty of 100 m or
  better. It is biased towards roads, tracks and iNaturalist users, so the
  absence of a record is not evidence of absence.
- **NVS (National Vegetation Survey Databank):** precisely located plots that
  record presence and absence, strong on forest. Access needs a data request to
  Manaaki Whenua. Probably the most valuable source if it can be obtained.
- **Covenant species records are excluded.** They are private and must not be
  used for training, matching or output.

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
