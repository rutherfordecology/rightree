---
title: Rightree
emoji: 🌳
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: Native plants expected at a site in Tairāwhiti
---

# Rightree

Right tree, right place. Draw a site in Tairāwhiti (Gisborne) and get the
native plant species expected there, from where they grow in environmentally
similar places nearby. Lists are split by successional stage (mature forest,
regenerating, open ground, wetland) and by plant layer.

A starting list to check on the ground, not a survey.

Source code: https://github.com/rutherfordecology/rightree

This Space is built from that repository by `scripts/build_space.py`. Don't
edit it here; changes are overwritten on the next build.

## Data in this Space

The `data/` folder holds the prepared inputs the app needs. Each comes under
its own licence:

- **Species records:** GBIF.org occurrence download, doi:10.15468/dl.x7fpqf,
  including the National Vegetation Survey Databank (NVS, Manaaki Whenua –
  Landcare Research; CC BY-NC 4.0, non-commercial use only), iNaturalist NZ
  and New Zealand herbaria. Filtered to native vascular plants located within
  100 m.
- **Environment:** New Zealand Environmental Data Stack (NZEnvDS) v1.1,
  McCarthy et al. 2021; CC BY 4.0. Clipped to the region.
- **Land cover:** Land Cover Database v6, Manaaki Whenua – Landcare Research,
  via LRIS; CC BY 4.0.
- **Wetlands:** Gisborne District Council Regional Wetland Assessment 2022
  (Morphum Environmental); CC BY 4.0.
- **Names:** New Zealand Threat Classification System (Department of
  Conservation).
- **Region boundary:** © OpenStreetMap contributors (ODbL).
