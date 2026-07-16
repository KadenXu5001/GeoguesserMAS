import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const dirs = [0, 90, 180, 270];
const names = { 0: "North / 0°", 90: "East / 90°", 180: "South / 180°", 270: "West / 270°" };
const colors = ["#ffcc66", "#74d6ff", "#ff7ca8", "#a8e063", "#c79cff", "#ff956b"];
const categories = ["driving_side_and_markings", "signs_and_language", "vehicles_and_plates", "infrastructure", "terrain_vegetation_and_climate", "architecture_and_settlement"];

function App() {
  const [panoramas, setPanoramas] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [active, setActive] = useState(0);
  const [result, setResult] = useState(null);
  const [opacity, setOpacity] = useState(72);
  const [status, setStatus] = useState("Choose a panorama from the MAS manifests.");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch("/api/panoramas").then((response) => response.json()).then((data) => {
      setPanoramas(data);
      if (data[0]) setSelectedId(data[0].id);
    }).catch(() => setStatus("Could not load the MAS panorama manifests."));
  }, []);

  const selected = panoramas.find((panorama) => panorama.id === selectedId);
  const src = selected ? `/media?path=${encodeURIComponent(selected.views[active])}` : null;
  const objects = useMemo(() => result ? categories.flatMap((key, index) =>
    (result[key]?.objects || []).filter((object) => object.heading === active && object.bbox)
      .map((object) => ({ ...object, key, color: colors[index] }))) : [], [result, active]);

  async function analyze() {
    if (!selected) return setStatus("Choose a panorama first.");
    setBusy(true); setResult(null); setStatus("Sending the MAS cardinal views to Gemini…");
    try {
      const response = await fetch("/api/analyze", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ paths: dirs.map((direction) => selected.views[direction]) }) });
      const data = await response.json();
      if (!response.ok) throw Error(data.error);
      setResult(data); setStatus("Analysis complete. Use the arrows to inspect each cardinal view.");
    } catch (error) { setStatus(error.message || "Analysis failed."); }
    finally { setBusy(false); }
  }

  return <main className="shell">
    <div className="eyebrow">Local vision lab · Gemini extraction-v1</div>
    <h1>See what the vision agent sees.</h1>
    <p className="intro">Choose one of the exact panoramas already used by MAS, run one Gemini vision pass, and inspect every returned bounding box directly on its cardinal views.</p>
    <div className="workspace">
      <section className="card">
        <div className="viewer">{src ? <div className="media"><img src={src} alt={names[active]} /><div className="layer" style={{ opacity: opacity / 100 }}>{objects.map((object, index) => { const box = object.bbox; return <div className="box" key={index} style={{ left: `${box.xmin / 10}%`, top: `${box.ymin / 10}%`, width: `${(box.xmax - box.xmin) / 10}%`, height: `${(box.ymax - box.ymin) / 10}%`, borderColor: object.color }}><span>{object.key.replaceAll("_", " ")} · {object.confidence}%</span></div>; })}</div></div> : <div className="status">Choose a MAS panorama to preview its cardinal views.</div>}</div>
        <div className="toolbar"><div className="nav"><button aria-label="Previous image" onClick={() => setActive(dirs[(dirs.indexOf(active) + dirs.length - 1) % dirs.length])}>←</button><span className="heading">{names[active]}</span><button aria-label="Next image" onClick={() => setActive(dirs[(dirs.indexOf(active) + 1) % dirs.length])}>→</button></div><label>Boxes {opacity}% <input className="range" type="range" min="0" max="100" value={opacity} onChange={(event) => setOpacity(event.target.value)} /></label></div>
        <div className="legend">{objects.map((object, index) => <span className="pill" key={index} style={{ borderLeft: `3px solid ${object.color}` }}>{object.observation}</span>)}</div>
      </section>
      <aside className="card side"><h2>MAS panorama</h2><label className="chooser"><strong>Select an existing MAS image set</strong><select value={selectedId} onChange={(event) => { setSelectedId(event.target.value); setResult(null); setActive(0); }}><option value="">Choose a panorama…</option>{panoramas.map((panorama) => <option key={panorama.id} value={panorama.id}>{panorama.country} · {panorama.id} · {panorama.split}</option>)}</select></label><p className="status">The selected set supplies the exact 0°, 90°, 180°, and 270° files from the MAS manifest.</p><button className="primary" disabled={busy || !selected} onClick={analyze}>{busy ? "Analyzing…" : "Run vision agent"}</button><p className={`status ${status.includes("failed") || status.includes("Could") ? "error" : ""}`}>{status}</p></aside>
    </div>
  </main>;
}

createRoot(document.getElementById("root")).render(<App />);
