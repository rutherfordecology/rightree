// Runs the Rightree model (scripts/predict.py) in the browser with Pyodide.
// The page posts {type: "predict", body}; the worker answers with
// {type: "status", text} while it works, then {type: "result", report} or
// {type: "error", message}. The page can also post {type: "prepare", region}
// when a region is chosen, so that region's records load before Predict.
const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/";
importScripts(PYODIDE + "pyodide.js");
const BASE = new URL("./", self.location).href;
const status = text => postMessage({type: "status", text});

let py = null, manifest = null;
const put = async f => {
  const r = await fetch(BASE + f);
  if (!r.ok) throw new Error(`Couldn't load ${f}`);
  const p = "/rightree/" + f;
  py.FS.mkdirTree(p.slice(0, p.lastIndexOf("/")));
  py.FS.writeFile(p, new Uint8Array(await r.arrayBuffer()));
};
const starting = (async () => {
  status("Loading Python…");
  py = await loadPyodide({indexURL: PYODIDE});
  await py.loadPackage(["numpy", "pandas", "shapely", "scikit-learn"]);
  manifest = await (await fetch(BASE + "files.json")).json();
  await Promise.all(manifest.common.map(put));
  // Grid tiles are fetched only when a site needs them (synchronous XHR is
  // allowed in workers, and the model's Python code is synchronous).
  py.globals.set("fetch_sync", path => {
    const x = new XMLHttpRequest();
    x.open("GET", BASE + path.replace(/^\/rightree\//, ""), false);
    x.responseType = "arraybuffer";
    x.send();
    if (x.status !== 200) throw new Error(`Couldn't load ${path}`);
    return new Uint8Array(x.response);
  });
  py.runPython(`
import contextlib, io, json, shutil, sys, traceback
from pathlib import Path
sys.path.insert(0, "/rightree/scripts")
import gridio, predict
gridio.FETCH = lambda p: bytes(fetch_sync(p).to_py())

def run_predict(region, rid, area):
    sys.argv = ["predict.py", region, rid, area]
    log = io.StringIO()
    try:
        with contextlib.redirect_stdout(log):
            predict.main()
    except SystemExit as e:
        return json.dumps({"error": str(e.code) if e.code else "Prediction failed"})
    except Exception as e:
        traceback.print_exc()
        return json.dumps({"error": f"Prediction failed: {e}"})
    d = Path("/rightree/data/predictions") / rid
    out = json.loads((d / "report.json").read_text(encoding="utf-8"))
    out["id"] = rid
    out["units_geojson"] = json.loads((d / "units.geojson").read_text(encoding="utf-8"))
    shutil.rmtree(d, ignore_errors=True)
    return json.dumps(out)
`);
  status("Ready");
})();
starting.catch(() => {});   // reported on the first prediction instead

// Each region's own files (its records, grid index and class names) load
// once, the first time that region is chosen or predicted.
const regionLoads = {};
function prepare(region) {
  if (!regionLoads[region]) {
    regionLoads[region] = (async () => {
      await starting;
      const files = manifest.regions[region];
      if (!files) throw new Error(`No data for region ${region}`);
      status("Loading records…");
      await Promise.all(files.map(put));
    })();
    regionLoads[region].catch(() => { delete regionLoads[region]; });   // retry next time
  }
  return regionLoads[region];
}

const slug = s => (s || "site").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "site";

onmessage = async e => {
  if (e.data.type === "prepare") {
    prepare(e.data.region).then(() => status("Ready"), () => {});   // errors show on Predict
    return;
  }
  const {body} = e.data;
  try {
    await prepare(body.region);
    status("Predicting…");
    const d = new Date(), pad = n => String(n).padStart(2, "0");
    const rid = `${slug(body.name)}-${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-` +
                `${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
    let area;
    if (body.file_b64) {
      const m = body.file_name.toLowerCase().match(/\.(kml|kmz|geojson|json)$/);
      const ext = !m ? "kml" : m[1] === "json" ? "geojson" : m[1];
      area = `/tmp/area.${ext}`;
      py.FS.writeFile(area, Uint8Array.from(atob(body.file_b64), c => c.charCodeAt(0)));
    } else {
      area = "/tmp/area.geojson";
      py.FS.writeFile(area, JSON.stringify(body.geojson));
    }
    const out = JSON.parse(py.globals.get("run_predict")(body.region, rid, area));
    if (out.error) postMessage({type: "error", message: out.error});
    else postMessage({type: "result", report: out});
  } catch (err) {
    postMessage({type: "error", message: err.message || String(err)});
  }
};
