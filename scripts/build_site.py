"""Build Rightree as a static website: the map page, the model (run in the
browser by Pyodide) and only the data a prediction needs. No server code.

Usage:
    python scripts/build_site.py [target]        # default: site/ (gitignored)

Serve the folder with any static host (a Hugging Face static Space, GitHub
Pages, Cloudflare Pages) or locally with `python scripts/serve.py`. If the
target is a git clone (e.g. of the Space), its .git is kept and everything
else replaced, so commit and push there to publish.
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ["predict.py", "gridio.py", "nztm.py"]

SPACE_README = """---
title: Rightree
emoji: 🌳
colorFrom: green
colorTo: gray
sdk: static
app_file: index.html
pinned: false
short_description: Native plants expected at a site in Tairāwhiti
---

# Rightree

Right tree, right place. Draw a site in Tairāwhiti (Gisborne) and get the
native plant species expected there, from where they grow in environmentally
similar places nearby. The model runs in your browser.

Source code: https://github.com/rutherfordecology/rightree. This Space is
built by `scripts/build_site.py`; don't edit it here.

## Data in this Space

Each dataset keeps its own licence:

- **Species records:** GBIF.org occurrence download, doi:10.15468/dl.x7fpqf,
  including the National Vegetation Survey Databank (NVS, Manaaki Whenua –
  Landcare Research; CC BY-NC 4.0, non-commercial use only), iNaturalist NZ
  and New Zealand herbaria. Native vascular plants located within 100 m.
- **Environment:** New Zealand Environmental Data Stack (NZEnvDS) v1.1,
  McCarthy et al. 2021; CC BY 4.0. Clipped to the region and tiled.
- **Land cover:** Land Cover Database v6, Manaaki Whenua – Landcare Research;
  CC BY 4.0.
- **Wetlands:** Gisborne District Council Regional Wetland Assessment 2022;
  CC BY 4.0.
- **Potential natural ecosystems:** this work uses a derivative of
  'Ecosystem Projector for NZ' by Eco-index (based on Potential Natural
  Vegetation, Manaaki Whenua), used under CC BY 4.0; gridded to 100 m.
- **Names:** New Zealand Threat Classification System (Department of
  Conservation).
- **Region boundary:** © OpenStreetMap contributors (ODbL).
"""


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "site"
    target.mkdir(parents=True, exist_ok=True)
    for p in target.iterdir():                       # clear the old build, keep .git
        if p.name != ".git":
            shutil.rmtree(p) if p.is_dir() else p.unlink()

    shutil.copy2(ROOT / "web" / "index.html", target / "index.html")
    shutil.copy2(ROOT / "web" / "worker.js", target / "worker.js")
    (target / "scripts").mkdir()
    for f in PY:
        shutil.copy2(ROOT / "scripts" / f, target / "scripts" / f)
    shutil.copytree(ROOT / "config", target / "config")

    data = target / "data"
    preload = [f"scripts/{f}" for f in PY] + [f"config/{p.name}" for p in (ROOT / "config").glob("*.json")]
    site = {"version": re.search(r"^## (v[\d.]+)", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M)[1],
            "regions": {}}
    genera = set()
    env_root = ROOT / "data" / "env"
    for env in sorted(p for p in env_root.iterdir() if (p / "tiles" / "grid.json").exists()):
        r = env.name
        shutil.copytree(env / "tiles", data / "env" / r / "tiles")
        for f in ["lcdb_classes.json", "region_stats.json", "potential_ecosystem_classes.json"]:
            if not (env / f).exists():
                continue
            shutil.copy2(env / f, data / "env" / r / f)
            preload.append(f"data/env/{r}/{f}")
        preload.append(f"data/env/{r}/tiles/grid.json")
        rec = ROOT / "data" / f"records_{r}_tagged.csv.gz"
        shutil.copy2(rec, data / rec.name)
        preload.append(f"data/{rec.name}")
        import pandas as pd
        names = pd.read_csv(rec, usecols=["species"])["species"].dropna()
        genera |= set(names.str.split().str[0])
        cite = json.loads((ROOT / "data" / f"citation_{r}.json").read_text(encoding="utf-8"))
        geo = json.loads((env / "region_osm_nominatim.json").read_text(encoding="utf-8"))[0]
        site["regions"][r] = {"name": geo.get("display_name", r), "geojson": geo["geojson"],
                              "citation": cite.get("citation"), "doi": cite.get("doi")}

    # Common names: only genera that occur in the records, from Occurd's NZTCS file
    nztcs = json.loads((ROOT.parent / "Occurd" / "nztcs.json").read_text(encoding="utf-8"))
    slim = {k: {f: v.get(f) for f in ("name", "maori", "common") if v.get(f)}
            for k, v in nztcs.items()
            if isinstance(v, dict) and v.get("name") and v["name"].split()[0] in genera
            and (v.get("maori") or v.get("common"))}
    (data / "nztcs_names.json").write_text(json.dumps(slim, ensure_ascii=False), encoding="utf-8")
    preload.append("data/nztcs_names.json")

    (target / "site.json").write_text(json.dumps(site, ensure_ascii=False), encoding="utf-8")
    (target / "files.json").write_text(json.dumps(preload), encoding="utf-8")
    (target / "README.md").write_text(SPACE_README, encoding="utf-8")
    # Hugging Face keeps binary files in LFS/Xet
    (target / ".gitattributes").write_text("*.bin filter=lfs diff=lfs merge=lfs -text\n"
                                           "*.gz filter=lfs diff=lfs merge=lfs -text\n", encoding="utf-8")

    files = [p for p in target.rglob("*") if p.is_file() and ".git" not in p.parts]
    print(f"Built {target}: {len(files)} files, {sum(p.stat().st_size for p in files) / 1e6:.1f} MB, "
          f"version {site['version']}, regions {', '.join(site['regions'])}")


if __name__ == "__main__":
    main()
