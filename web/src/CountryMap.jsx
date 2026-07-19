import React, { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const DEFAULT_STYLE = {
  color: "#6f8791",
  weight: 0.75,
  fillColor: "#163344",
  fillOpacity: 0.06,
};
const HOVER_STYLE = {
  color: "#9cdcc5",
  weight: 1.5,
  fillColor: "#6ee7bd",
  fillOpacity: 0.18,
};
const SELECTED_STYLE = {
  stroke: false,
  weight: 0,
  fillColor: "#6ee7bd",
  fillOpacity: 0.5,
};

export default function CountryMap({ selectedCountry, onSelect, submitted }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const countryLayerRef = useRef(null);
  const selectedRef = useRef(selectedCountry);
  const onSelectRef = useRef(onSelect);
  const submittedRef = useRef(submitted);
  const [expanded, setExpanded] = useState(false);
  const [status, setStatus] = useState("Loading country boundaries…");

  useEffect(() => { selectedRef.current = selectedCountry; }, [selectedCountry]);
  useEffect(() => { onSelectRef.current = onSelect; }, [onSelect]);
  useEffect(() => { submittedRef.current = submitted; }, [submitted]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return undefined;
    const map = L.map(containerRef.current, {
      center: [18, 0],
      zoom: 2,
      minZoom: 1,
      maxZoom: 7,
      worldCopyJump: true,
      zoomControl: true,
      attributionControl: true,
    });
    mapRef.current = map;
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap contributors",
      maxZoom: 19,
    }).addTo(map);

    let cancelled = false;
    fetch("/countries.geojson").then((response) => {
      if (!response.ok) throw new Error(`Country boundary request failed (${response.status})`);
      return response.json();
    }).then((data) => {
      if (cancelled) return;
      const countryLayer = L.geoJSON(null, {
        style: (feature) => feature.properties.iso2 === selectedRef.current?.iso2
          ? SELECTED_STYLE
          : DEFAULT_STYLE,
        onEachFeature: (feature, layer) => {
          layer.bindTooltip(feature.properties.name, { sticky: true, direction: "top" });
          layer.on({
            mouseover: () => {
              if (feature.properties.iso2 !== selectedRef.current?.iso2) layer.setStyle(HOVER_STYLE);
            },
            mouseout: () => {
              if (feature.properties.iso2 !== selectedRef.current?.iso2) layer.setStyle(DEFAULT_STYLE);
            },
            click: () => {
              if (!submittedRef.current) {
                onSelectRef.current({ iso2: feature.properties.iso2, name: feature.properties.name });
              }
            },
          });
        },
      }).addTo(map);
      let loadedCount = 0;
      for (const feature of data.features || []) {
        try {
          countryLayer.addData(feature);
          loadedCount += 1;
        } catch (error) {
          console.warn(`Skipping invalid boundary for ${feature.properties?.name || "unknown country"}.`, error);
        }
      }
      if (!loadedCount) throw new Error("No valid country boundaries were found.");
      countryLayerRef.current = countryLayer;
      setStatus("Choose a country");
    }).catch((error) => {
      console.error("Country boundaries could not be loaded.", error);
      setStatus("Country boundaries could not be loaded.");
    });
    return () => {
      cancelled = true;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    countryLayerRef.current?.eachLayer((layer) => {
      layer.setStyle(layer.feature.properties.iso2 === selectedCountry?.iso2
        ? SELECTED_STYLE
        : DEFAULT_STYLE);
    });
  }, [selectedCountry]);

  useEffect(() => {
    const timeout = window.setTimeout(() => mapRef.current?.invalidateSize(), 240);
    return () => window.clearTimeout(timeout);
  }, [expanded]);

  return <section
    className={`guess-map-card ${expanded ? "expanded" : ""}`}
    onMouseEnter={() => setExpanded(true)}
    onMouseLeave={() => setExpanded(false)}
  >
    <button
      className="map-expand-toggle"
      onClick={() => setExpanded((value) => !value)}
      aria-expanded={expanded}
      aria-label={expanded ? "Collapse country map" : "Expand country map"}
    >
      <span>{selectedCountry?.name || status}</span>
      <span>{expanded ? "−" : "+"}</span>
    </button>
    <div ref={containerRef} className="leaflet-map" aria-label="Interactive country selection map" />
  </section>;
}
