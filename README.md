# Rightree

Right tree, right place. Draw a boundary and get the native plant species that
are expected there, based on where those species have been recorded in
environmentally similar places nearby.

Rightree predicts plant communities, not just trees: shrubs, ferns, sedges and
herbs come out of the same analysis. The list is meant to inform management and
revegetation planning. It is a starting point to be checked on the ground, not
a survey.

Status: prototype (v0.2.0). Occurrence data and environmental layers load;
nothing predicts yet. See [`docs/design.md`](docs/design.md).

## Loading occurrence data

1. In Occurd's Big Data Mode, draw the area, tick Angiosperms, Gymnosperms and
   Ferns & allies, clear the From date, and fetch.
2. Save GBIF's zip, keeping its name (`<downloadkey>.zip`), in `data/`.
3. Run:

```bash
python scripts/load_gbif.py data/<downloadkey>.zip <name>
python scripts/summarise_gbif.py <name>
```

## How it works (planned)

1. **Draw a polygon.** Rightree splits it into units that differ in
   environment: land environment (LENZ), soil, geology, slope and aspect.
2. **Describe each unit** by its environmental values: rainfall, temperature,
   soil, geology, slope, aspect and current land cover (LCDB).
3. **Find similar places** within the same or neighbouring ecological
   districts, so biogeographic limits are respected.
4. **Look at what has been recorded there.** Uses high-precision GBIF records,
   and NVS plots if access is granted.
5. **Return a ranked species list for each unit**, as the percentage of similar
   sites a species was recorded in. Results are split by land cover, so the list
   shows a succession sequence: what grows in mānuka/kānuka on these sites, and
   what grows in mature forest.

## Related tools

- **Occurd:** shows what *has been* recorded in an area. Rightree says what
  *should be* there.
- **inferrd:** tracks vegetation change over time from Sentinel-2.
- **Report workflow:** Rightree exports data into `projects/<job>/data/`. It
  does not write reports.
