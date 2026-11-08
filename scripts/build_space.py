"""Assemble the Hugging Face Space folder: the app, the data a prediction
needs, and a Dockerfile. Nothing else (no raw downloads, no LCDB polygons,
no API keys).

Usage:
    python scripts/build_space.py [target]      # default ../rightree-space

The target can be a clone of the Space's git repo: its .git is left alone and
everything else is replaced, so `git add -A && git commit && git push` there
publishes the new build.
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from predict import VARS  # noqa: E402

# Grid layers predict.py reads besides the model inputs
EXTRA_TIFS = ["elevation", "lcdb_class", "wetland_status"]
ENV_JSON = ["lcdb_classes.json", "region_osm_nominatim.json"]


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "rightree-space"
    target.mkdir(parents=True, exist_ok=True)
    for p in target.iterdir():                       # clear the old build, keep .git
        if p.name == ".git":
            continue
        shutil.rmtree(p) if p.is_dir() else p.unlink()

    for f in ["Dockerfile", "requirements.txt", "README.md"]:
        shutil.copy2(ROOT / "space" / f, target / f)
    shutil.copy2(ROOT / "CHANGELOG.md", target / "CHANGELOG.md")
    (target / "scripts").mkdir()
    for f in ["predict.py", "serve.py"]:
        shutil.copy2(ROOT / "scripts" / f, target / "scripts" / f)
    shutil.copytree(ROOT / "web", target / "web")
    shutil.copytree(ROOT / "config", target / "config")

    data = target / "data"
    regions = [p.name for p in (ROOT / "data" / "env").iterdir() if (p / "region_osm_nominatim.json").exists()]
    for r in regions:
        src, dst = ROOT / "data" / "env" / r, data / "env" / r
        dst.mkdir(parents=True)
        for v in VARS + EXTRA_TIFS:
            shutil.copy2(src / f"{v}.tif", dst / f"{v}.tif")
        for f in ENV_JSON:
            shutil.copy2(src / f, dst / f)
        for f in [f"records_{r}_tagged.csv.gz", f"citation_{r}.json"]:
            shutil.copy2(ROOT / "data" / f, data / f)

    # Common names only, instead of Occurd's full NZTCS file
    nztcs = json.loads((ROOT.parent / "Occurd" / "nztcs.json").read_text(encoding="utf-8"))
    slim = {k: {f: v.get(f) for f in ("name", "maori", "common")}
            for k, v in nztcs.items() if isinstance(v, dict) and v.get("name")}
    (data / "nztcs_names.json").write_text(json.dumps(slim, ensure_ascii=False), encoding="utf-8")

    # Hugging Face stores binary files with Git LFS / Xet
    (target / ".gitattributes").write_text("*.tif filter=lfs diff=lfs merge=lfs -text\n"
                                           "*.gz filter=lfs diff=lfs merge=lfs -text\n", encoding="utf-8")
    (target / ".gitignore").write_text("data/predictions/\n__pycache__/\n", encoding="utf-8")

    size = sum(p.stat().st_size for p in target.rglob("*") if p.is_file() and ".git" not in p.parts)
    print(f"Built {target}: regions {', '.join(regions)}, {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
