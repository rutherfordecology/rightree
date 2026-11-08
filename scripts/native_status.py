"""Decide whether each species name is a New Zealand native.

1. `resolve_names.mjs` resolves each name to an NZTCS taxon with Occurd's
   but-is-it-threatened resolver, trying NZOR's accepted name first (synonyms,
   e.g. Zealandia pustulata -> Lecanopteris pustulata), then the name as given.
2. Native = that taxon's bioStatus is Endemic or Non-endemic, and its category
   is not "Introduced and Naturalised".
3. Names that don't resolve are treated as not native: NZTCS assesses every
   native vascular plant but few exotics. They are listed for review, and
   `config/native_overrides.json` can force a verdict.

Usage:
    python scripts/native_status.py tairawhiti
Writes data/native_status_<name>.csv (one row per species, for review).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
NZTCS_PATH = ROOT.parent / "Occurd" / "nztcs.json"
NATIVE_BIO = {"Endemic", "Non-endemic"}


INFRA = re.compile(r"^(\S+ \S+ (?:subsp\.|var\.|f\.) [a-z-]+)")


def match_name(species, scientific_name, rank):
    """The name to match against NZTCS: the record's own subspecies, variety or
    form when it was identified that far, otherwise the species."""
    if rank in ("SUBSPECIES", "VARIETY", "FORM") and isinstance(scientific_name, str):
        m = INFRA.match(scientific_name)
        if m:
            return m.group(1)
    return species


def classify(names):
    """DataFrame indexed by name: native, how, nztcs_name, bioStatus, category."""
    names = sorted(set(names))
    tmp = ROOT / "data" / "_names.json"
    res_path = ROOT / "data" / "_resolved.json"
    tmp.write_text(json.dumps(names), encoding="utf-8")
    subprocess.run(["node", str(ROOT / "scripts" / "resolve_names.mjs"), str(tmp), str(res_path)], check=True)
    resolved = json.loads(res_path.read_text(encoding="utf-8"))
    tmp.unlink(); res_path.unlink()

    nztcs = json.loads(NZTCS_PATH.read_text(encoding="utf-8"))
    by_name = {v["name"]: v for v in nztcs.values() if isinstance(v, dict) and v.get("name")}
    overrides = json.loads((ROOT / "config" / "native_overrides.json").read_text(encoding="utf-8"))["overrides"]

    # Infraspecific taxa under each species, to spot species NZTCS splits.
    infra = {}
    for nm in by_name:
        if INFRA.match(nm) or len(nm.split()) >= 4:
            infra.setdefault(" ".join(nm.split()[:2]), []).append(nm)

    rows = []
    for n in names:
        r = resolved.get(n)
        v = by_name.get(r["n"]) if r else None
        bio, cat = (v or {}).get("bioStatus"), (v or {}).get("category")
        native = bool(v) and bio in NATIVE_BIO and cat != "Introduced and Naturalised"
        how = r["via"] if r else "not in nztcs"
        nztcs_name = r["n"] if r else None
        # A species-level record can't be pinned to one of several subspecies
        # or varieties. The resolver's nominate pass would pick e.g. Oplismenus
        # hirtellus subsp. hirtellus (At Risk) when NZ's common plant is subsp.
        # imbecillis. Keep the species: native if any of its taxa is native, and
        # a threat category only if they all share it.
        if r and "nominate" in r["via"]:
            sp = " ".join(r["n"].split()[:2])
            kids = [by_name[k] for k in infra.get(sp, [])]
            if len(kids) > 1:
                cats = {k.get("category") for k in kids}
                nat = [k for k in kids if k.get("bioStatus") in NATIVE_BIO and k.get("category") != "Introduced and Naturalised"]
                native = bool(nat)
                bio = nat[0]["bioStatus"] if nat else kids[0].get("bioStatus")
                cat = cats.pop() if len(cats) == 1 else None
                how = r["via"].replace("nominate", "species level; NZTCS splits it")
                nztcs_name = sp
        if n in overrides:
            o = overrides[n]
            native, how, nztcs_name = o["native"], "override: " + o["why"], o.get("nztcs_name")
            v = by_name.get(nztcs_name) or {}
            bio, cat = v.get("bioStatus"), v.get("category")
        rows.append({"species": n, "native": native, "how": how,
                     "nztcs_name": nztcs_name, "bioStatus": bio, "category": cat})
    return pd.DataFrame(rows).set_index("species")


def main():
    """Review table over every species in the load, natives and exotics."""
    name = sys.argv[1]
    df = pd.concat([pd.read_csv(ROOT / "data" / f"records_{name}{s}.csv.gz",
                                usecols=["species", "scientificName", "taxonRank"], low_memory=False)
                    for s in ("", "_exotic")])
    counts = pd.Series([match_name(*t) for t in zip(df["species"], df["scientificName"], df["taxonRank"])]).value_counts()
    st = classify(counts.index)
    st["records"] = counts
    st = st.sort_values("records", ascending=False)
    out = ROOT / "data" / f"native_status_{name}.csv"
    st.to_csv(out)
    print(st.groupby(["native"]).agg(species=("records", "size"), records=("records", "sum")).to_string())
    print("\nHow natives matched:", st[st.native].how.str.replace(r"^nzor synonym, ", "", regex=True).value_counts().to_dict())
    print("\nNot native, most records: " + ", ".join(
        f"{s} ({n})" for s, n in st.loc[~st["native"], "records"].head(60).items()))
    print(f"\nWrote {out.name}")


if __name__ == "__main__":
    main()
