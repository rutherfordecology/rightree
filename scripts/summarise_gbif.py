"""Summarise cleaned records: sources, NVS plot visits, species, years, map.

Usage:
    python scripts/summarise_gbif.py tairawhiti
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

name = sys.argv[1]
root = Path(__file__).resolve().parent.parent
df = pd.read_csv(root / "data" / f"records_{name}.csv.gz", low_memory=False)

lines = [f"# Records summary: {name}", ""]
lines.append(f"- Records kept: {len(df):,}; species: {df['species'].nunique():,}")
for src, g in df.groupby("source"):
    lines.append(f"- {src}: {len(g):,} records, {g['species'].nunique():,} species, "
                 f"{g['visit'].nunique():,} visits")

nvs = df[df["source"] == "NVS"]
v = nvs.groupby("visit")
sizes = v["species"].nunique()
yrs = v["year"].first().dropna()
lines += [
    "",
    "## NVS plot visits (dataset + location + date)",
    f"- Visits: {len(sizes):,}; distinct locations: {nvs.groupby(['decimalLatitude', 'decimalLongitude']).ngroups:,}",
    f"- Species per visit: median {sizes.median():.0f} (10th pct {sizes.quantile(.1):.0f}, 90th pct {sizes.quantile(.9):.0f})",
    f"- Visit years: {int(yrs.min())} to {int(yrs.max())}, median {int(yrs.median())}",
    f"- Visits by decade: " + ", ".join(f"{int(d)}s {n}" for d, n in (yrs // 10 * 10).value_counts().sort_index().items()),
    "",
    "## Most widespread species (share of NVS visits)",
]
top = nvs.groupby("species")["visit"].nunique().sort_values(ascending=False).head(25)
lines += [f"- {s}: {n:,} ({n / len(sizes):.0%})" for s, n in top.items()]

out = root / "data" / f"summary_{name}.md"
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))

fig, ax = plt.subplots(figsize=(7, 8))
for src, colour, size in [("other", "#999", 2), ("iNaturalist", "#2a9d8f", 2), ("NVS", "#c0392b", 4)]:
    g = df[df["source"] == src].drop_duplicates(["decimalLatitude", "decimalLongitude"])
    ax.scatter(g["decimalLongitude"], g["decimalLatitude"], s=size, c=colour, label=f"{src} ({len(g):,} locations)")
ax.set_aspect(1 / 0.78)  # rough lon/lat scaling at 38.5 S
ax.legend(loc="lower right", markerscale=4)
ax.set_title(f"Vascular plant records within 100 m: {name}")
fig.tight_layout()
fig.savefig(root / "data" / f"map_{name}.png", dpi=130)
print(f"\nWrote {out.name} and map_{name}.png")
