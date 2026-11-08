"""Load a GBIF SIMPLE_CSV download zip (from Occurd's Big Data Mode) and
keep the records Rightree can use.

Keeps vascular plant records that are PRESENT, identified to species, and
located to within 100 m. Drops Pl@ntNet's automatic image IDs. NVS plot
visits are reconstructed as (dataset, location, date), because SIMPLE_CSV
has no eventID.

Usage:
    python scripts/load_gbif.py data/0006587-261104105008071.zip tairawhiti
Writes:
    data/records_<name>.csv.gz   cleaned records
    data/citation_<name>.json    download key, DOI, counts, licences
"""
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests

NVS = "788439f0-3b56-11dc-8c19-b8a03c50a862"
INAT = "50c9509d-22c7-4a22-a47d-8c48425ef4a7"
PLANTNET_AUTO = "14d5676a-2c54-4f94-9023-1e8dcd822aa0"
MAX_UNCERTAINTY_M = 100

COLS = [
    "gbifID", "datasetKey", "occurrenceStatus", "basisOfRecord",
    "kingdom", "phylum", "class", "order", "family", "genus", "species",
    "taxonRank", "scientificName", "speciesKey", "taxonKey",
    "decimalLatitude", "decimalLongitude", "coordinateUncertaintyInMeters",
    "eventDate", "year", "establishmentMeans", "license", "issue",
]


def main():
    zpath, name = Path(sys.argv[1]), sys.argv[2]
    key = zpath.stem
    root = Path(__file__).resolve().parent.parent

    with zipfile.ZipFile(zpath) as z:
        member = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(member) as f:
            df = pd.read_csv(f, sep="\t", usecols=lambda c: c in COLS,
                             dtype=str, quoting=3, on_bad_lines="warn")
    raw = len(df)

    df["coordinateUncertaintyInMeters"] = pd.to_numeric(df["coordinateUncertaintyInMeters"], errors="coerce")
    for c in ("decimalLatitude", "decimalLongitude"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["year"] = pd.to_numeric(df["year"], errors="coerce")

    steps = {"raw": raw}
    df = df[df["phylum"] == "Tracheophyta"]; steps["vascular"] = len(df)
    df = df[df["occurrenceStatus"].fillna("PRESENT") == "PRESENT"]; steps["present"] = len(df)
    df = df[df["species"].notna()]; steps["to_species"] = len(df)
    df = df[df["datasetKey"] != PLANTNET_AUTO]; steps["not_plantnet_auto"] = len(df)
    df = df[df["coordinateUncertaintyInMeters"] <= MAX_UNCERTAINTY_M]; steps["within_100m"] = len(df)

    df["source"] = df["datasetKey"].map({NVS: "NVS", INAT: "iNaturalist"}).fillna("other")
    date = df["eventDate"].fillna("").str.slice(0, 10)
    df["visit"] = (df["datasetKey"] + "|" + df["decimalLatitude"].round(5).astype(str) + "|"
                   + df["decimalLongitude"].round(5).astype(str) + "|" + date)

    out = root / "data" / f"records_{name}.csv.gz"
    df.to_csv(out, index=False)

    meta = requests.get(f"https://api.gbif.org/v1/occurrence/download/{key}", timeout=30).json()
    citation = {
        "downloadKey": key,
        "doi": meta.get("doi"),
        "created": meta.get("created"),
        "totalRecords": meta.get("totalRecords"),
        "filterSteps": steps,
        "licences": df["license"].value_counts().to_dict(),
        "citation": f"GBIF.org ({(meta.get('created') or '')[:10]}) GBIF Occurrence Download https://doi.org/{meta.get('doi')}",
    }
    (root / "data" / f"citation_{name}.json").write_text(json.dumps(citation, indent=2), encoding="utf-8")
    print(json.dumps(citation, indent=2))


if __name__ == "__main__":
    main()
