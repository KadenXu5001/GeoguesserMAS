import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import CountryMap from "./CountryMap";
import PanoramaViewer from "./PanoramaViewer";
import { analyzeRound, createRound, getRound, submitGuess } from "./api";
import "./style.css";

const DIRECTIONS = [0, 90, 180, 270];
const DIRECTION_NAMES = { 0: "North", 90: "East", 180: "South", 270: "West" };
const CATEGORY_COLORS = {
  driving_side_and_markings: "#9b8cff",
  signs_and_language: "#ffcf68",
  vehicles_and_plates: "#ff7e91",
  infrastructure: "#4dd7b4",
  terrain_vegetation_and_climate: "#5db8ff",
  architecture_and_settlement: "#ff9f68",
};

function Icon({ name, size = 20 }) {
  const paths = {
    arrowLeft: <path d="m14.5 5-7 7 7 7" />,
    arrowRight: <path d="m9.5 5 7 7-7 7" />,
    compass: <><circle cx="12" cy="12" r="8.5" /><path d="m15.2 8.8-1.7 4.7-4.7 1.7 1.7-4.7 4.7-1.7Z" /></>,
    eye: <><path d="M2.5 12s3.4-5.5 9.5-5.5 9.5 5.5 9.5 5.5-3.4 5.5-9.5 5.5S2.5 12 2.5 12Z" /><circle cx="12" cy="12" r="2.5" /></>,
    globe: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 2.5 3.7 5.5 3.7 9S14.5 18.5 12 21c-2.5-2.5-3.7-5.5-3.7-9S9.5 5.5 12 3Z" /></>,
    layers: <><path d="m12 3-9 5 9 5 9-5-9-5Z" /><path d="m3 12 9 5 9-5M3 16l9 5 9-5" /></>,
    spark: <path d="m12 2 1.5 5.2L19 9l-5.5 1.8L12 16l-1.5-5.2L5 9l5.5-1.8L12 2ZM19 15l.7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7L19 15Z" />,
    zoom: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m15.5 15.5 4 4M10.5 8v5M8 10.5h5" /></>,
  };
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

function navigate(path, setPath) {
  window.history.pushState({}, "", path);
  setPath(path);
  window.scrollTo({ top: 0 });
}

function Brand({ onClick, compact = false }) {
  return <button className={`brand ${compact ? "compact" : ""}`} onClick={onClick} aria-label="Go to the home screen">
    <span className="brand-mark"><Icon name="compass" size={22} /></span>
    <span>Atlas<span>Lens</span></span>
  </button>;
}

function AppHeader({ onHome }) {
  return <header className="site-header"><Brand onClick={onHome} /><div className="prototype-pill"><span /> Vision MAS training</div></header>;
}

function WorldMap({ onExplore }) {
  return <div className="world-map" aria-label="World training map">
    <svg viewBox="0 0 1000 480" role="img" aria-label="Stylized world map">
      <defs><linearGradient id="ocean" x1="0" x2="1" y1="0" y2="1"><stop stopColor="#18344d" /><stop offset="1" stopColor="#0d2134" /></linearGradient><linearGradient id="land" x1="0" x2="1"><stop stopColor="#63c6a4" /><stop offset="1" stopColor="#7ed1b3" /></linearGradient></defs>
      <rect width="1000" height="480" rx="24" fill="url(#ocean)" />
      <g opacity=".17" stroke="#b5dbed"><path d="M0 96h1000M0 192h1000M0 288h1000M0 384h1000M200 0v480M400 0v480M600 0v480M800 0v480" /><path d="M0 240h1000" strokeWidth="2" /></g>
      <g fill="url(#land)" stroke="#9fe3c9" strokeWidth="2"><path d="M84 98 142 58l85 12 48 40 56 5 42 44-34 30-45-7-20 45-38 13-26 66-24-21 8-58-39-27-55-29-34-42 18-31Z" /><path d="m279 287 49 21 31 48-17 68-38 41-22-44 7-48-31-52 21-34Z" /><path d="m429 101 58-31 74 18 38-18 82 18 84-18 55 31 87 23-29 33-71-2-32 31-73 2-41 42-39-11-20-39-66-5-40-31-47-8 30-35Z" /><path d="m522 205 65 6 41 40-12 75-45 69-41-29-10-65-32-43 34-53Z" /><path d="m805 327 46-29 63 18 25 43-37 37-68-7-29-62Z" /><path d="m901 239 21-12 18 14-15 17-24-19Z" /></g>
    </svg>
    {[["North America","north-america"],["Europe","europe"],["Asia","asia"],["Africa","africa"]].map(([label, className]) => <button key={label} className={`map-pin ${className}`} onClick={onExplore}><span />{label}</button>)}
    <div className="map-caption"><Icon name="globe" size={17} /> Select a region to begin training</div>
  </div>;
}

function HomeScreen({ starting, error, onExplore }) {
  return <div className="home-page"><AppHeader onHome={() => {}} /><main className="page-shell">
    <section className="hero"><div className="eyebrow"><span /> Explore · Observe · Learn</div><h1>Learn to read the <em>world.</em></h1><p>Train your geographic intuition, explore panoramic clues, and see how a vision agent reasons about place.</p></section>
    <WorldMap onExplore={onExplore} />
    <section className="training-section"><div><div className="eyebrow"><span /> Training modes</div><h2>Choose your challenge</h2><p>Start with worldwide exploration. More focused modes are on the way.</p>{error && <p className="home-error">{error}</p>}</div><div className="mode-grid">
      <button className="mode-card active" disabled={starting} onClick={onExplore}><span className="mode-icon"><Icon name="globe" size={28} /></span><span className="mode-copy"><strong>World</strong><small>{starting ? "Preparing a panorama…" : "Start a training example"}</small></span><span className="card-arrow"><Icon name="arrowRight" /></span></button>
      <button className="mode-card" disabled><span className="mode-icon"><span className="flag">US</span></span><span className="mode-copy"><strong>USA</strong><small>Coming soon</small></span><span className="soon">Soon</span></button>
      <button className="mode-card" disabled><span className="mode-icon"><Icon name="spark" size={27} /></span><span className="mode-copy"><strong>More modes</strong><small>In development</small></span><span className="soon">Soon</span></button>
    </div></section>
  </main><footer><span>AtlasLens</span><span>Learning the world, one clue at a time.</span></footer></div>;
}

function ResultCard({ result, loadingNext, onNext }) {
  return <section className={`training-result ${result.correct ? "correct" : "incorrect"}`} aria-live="polite">
    <div className="result-symbol">{result.correct ? "✓" : "×"}</div>
    <div><span>{result.correct ? "Correct" : "Not quite"}</span><strong>{result.correctCountry.name}</strong><small>Your guess: {result.selectedCountry.name}</small></div>
    <button onClick={onNext} disabled={loadingNext}>{loadingNext ? "Loading…" : "Next example"}<Icon name="arrowRight" size={17} /></button>
  </section>;
}

function WorldTrainingScreen({ round, state, setState, onHome, onVision, onNext }) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function guess() {
    if (!state.selectedCountry || state.result || submitting) return;
    setSubmitting(true); setError("");
    try {
      const result = await submitGuess(round.roundId, state.selectedCountry.iso2);
      setState((current) => ({ ...current, result }));
    } catch (requestError) { setError(requestError.message); }
    finally { setSubmitting(false); }
  }

  return <main className="training-page">
    <PanoramaViewer panoramaUrl={round.panoramaUrl} viewState={state.viewState} onViewStateChange={(viewState) => setState((current) => ({ ...current, viewState }))} />
    <div className="panorama-vignette" />
    <div className="training-topbar"><Brand compact onClick={onHome} /><div className="training-label"><span /> World training · Location hidden</div><button className="vision-hint" onClick={onVision}><Icon name="eye" size={20} /><span><strong>Vision Agent Guide</strong><small>Optional hint</small></span></button></div>
    <div className="panorama-help"><Icon name="compass" /><span><strong>Look around</strong>Drag to rotate · Scroll to zoom</span></div>
    <div className="guess-dock">
      <CountryMap selectedCountry={state.selectedCountry} onSelect={(selectedCountry) => setState((current) => ({ ...current, selectedCountry }))} submitted={Boolean(state.result)} />
      {!state.result && <div className="guess-actions"><div><span>Your country</span><strong>{state.selectedCountry?.name || "Choose on the map"}</strong></div><button className="guess-button" disabled={!state.selectedCountry || submitting} onClick={guess}>{submitting ? "Checking…" : "Guess"}</button></div>}
      {error && <div className="guess-error">{error}</div>}
    </div>
    {state.result && <ResultCard result={state.result} loadingNext={state.loadingNext} onNext={onNext} />}
  </main>;
}

function VisionImage({ round, direction, objects }) {
  return <article className="vision-view"><div className="vision-image"><img src={round.viewUrls[direction]} alt={`${DIRECTION_NAMES[direction]} cardinal view`} /><div className="bbox-layer">{objects.map((object, index) => <div className="bbox" key={`${object.key}-${index}`} style={{ left: `${object.bbox.xmin / 10}%`, top: `${object.bbox.ymin / 10}%`, width: `${(object.bbox.xmax - object.bbox.xmin) / 10}%`, height: `${(object.bbox.ymax - object.bbox.ymin) / 10}%`, borderColor: object.color }}><span style={{ background: object.color }}>{object.key.replaceAll("_", " ")} · {object.confidence}%</span></div>)}</div><span className="direction-tag">{DIRECTION_NAMES[direction]} · {direction}°</span></div></article>;
}

function VisionScreen({ round, state, setState, onBack }) {
  useEffect(() => {
    if (state.analysis || state.analysisLoading || state.analysisError) return;
    setState((current) => ({ ...current, analysisLoading: true, analysisError: "" }));
    analyzeRound(round.roundId).then((payload) => {
      setState((current) => ({ ...current, analysis: payload.analysis, analysisLoading: false }));
    }).catch((error) => {
      setState((current) => ({ ...current, analysisError: error.message, analysisLoading: false }));
    });
  }, [round.roundId, state.analysisError]);

  const objectsByDirection = useMemo(() => Object.fromEntries(DIRECTIONS.map((direction) => [direction, Object.entries(CATEGORY_COLORS).flatMap(([key, color]) => (state.analysis?.[key]?.objects || []).filter((object) => object.heading === direction && object.bbox).map((object) => ({ ...object, key, color })))])), [state.analysis]);
  const observationCount = Object.values(objectsByDirection).reduce((sum, objects) => sum + objects.length, 0);

  return <div className="vision-page"><AppHeader onHome={onBack} /><main className="page-shell vision-shell">
    <section className="page-heading vision-heading"><button className="back-link" onClick={onBack}><Icon name="arrowLeft" size={17} /> Back to panorama</button><div><span>Optional hint · Vision MAS</span><h1>See what the agent sees</h1></div><div className="place-id">Answer remains hidden</div></section>
    <section className="vision-intro"><div><div className="eyebrow"><span /> Four-view analysis</div><h2>Visual evidence, made visible.</h2><p>The agent scans all four cardinal views. Colored boxes highlight the evidence it uses to reason about this place.</p></div>{state.analysisLoading && <div className="analysis-state"><span className="spinner" />Analyzing once for this panorama…</div>}</section>
    <section className="vision-grid">{DIRECTIONS.map((direction) => <VisionImage key={direction} round={round} direction={direction} objects={objectsByDirection[direction]} />)}</section>
    {state.analysisError && <div className="analysis-empty error"><Icon name="eye" size={28} /><strong>Analysis could not be completed</strong><span>{state.analysisError}</span><button onClick={() => setState((current) => ({ ...current, analysisError: "", analysisLoading: false }))}>Try again</button></div>}
    <section className="evidence-panel"><div className="evidence-header"><div><span className="section-label"><Icon name="layers" size={18} /> Bounding boxes guide</span><h2>Evidence the agent noticed</h2></div><span>{observationCount} observations</span></div><div className="evidence-list">{Object.entries(CATEGORY_COLORS).map(([key, color]) => <div className="evidence-key" key={key}><span style={{ background: color }} /><div><strong>{key.replaceAll("_", " ")}</strong><small>{(state.analysis?.[key]?.objects || []).length} detected</small></div></div>)}</div></section>
  </main></div>;
}

function LoadingScreen({ message, onHome }) {
  return <div className="route-loading"><Brand onClick={onHome} /><span className="spinner" /><strong>{message}</strong></div>;
}

function App() {
  const [path, setPath] = useState(window.location.pathname);
  const [round, setRound] = useState(null);
  const [roundState, setRoundState] = useState({ selectedCountry: null, result: null, viewState: { yaw: 0, pitch: 0, zoom: 35 }, analysis: null, analysisLoading: false, analysisError: "", loadingNext: false });
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const visionMatch = path.match(/^\/world\/([0-9a-f-]+)\/vision$/i);
  const worldMatch = path.match(/^\/world\/([0-9a-f-]+)$/i);
  const routeRoundId = (visionMatch || worldMatch)?.[1];

  useEffect(() => {
    if (!routeRoundId || round?.roundId === routeRoundId) return;
    setError("");
    getRound(routeRoundId).then((loadedRound) => {
      setRound(loadedRound);
      setRoundState((current) => ({ ...current, result: loadedRound.result || null }));
    }).catch((requestError) => setError(requestError.message));
  }, [routeRoundId, round?.roundId]);

  const go = (nextPath) => navigate(nextPath, setPath);
  const resetRoundState = () => setRoundState({ selectedCountry: null, result: null, viewState: { yaw: 0, pitch: 0, zoom: 35 }, analysis: null, analysisLoading: false, analysisError: "", loadingNext: false });

  async function startRound() {
    setStarting(true); setError("");
    try {
      const seen = JSON.parse(sessionStorage.getItem("atlaslens.seenRounds") || "[]");
      const nextRound = await createRound(seen);
      const nextSeen = [...seen, nextRound.roundId].slice(-100);
      sessionStorage.setItem("atlaslens.seenRounds", JSON.stringify(nextSeen));
      setRound(nextRound); resetRoundState();
      go(`/world/${nextRound.roundId}`);
    } catch (requestError) { setError(requestError.message); }
    finally { setStarting(false); }
  }

  async function nextRound() {
    setRoundState((current) => ({ ...current, loadingNext: true }));
    await startRound();
  }

  if (!routeRoundId) return <HomeScreen starting={starting} error={error} onExplore={startRound} />;
  if (!round || round.roundId !== routeRoundId) return <LoadingScreen message={error || "Preparing your panorama…"} onHome={() => go("/")} />;
  if (visionMatch) return <VisionScreen round={round} state={roundState} setState={setRoundState} onBack={() => go(`/world/${round.roundId}`)} />;
  return <WorldTrainingScreen round={round} state={roundState} setState={setRoundState} onHome={() => go("/")} onVision={() => go(`/world/${round.roundId}/vision`)} onNext={nextRound} />;
}

createRoot(document.getElementById("root")).render(<App />);
