import React, { useEffect, useRef } from "react";
import { Viewer } from "@photo-sphere-viewer/core";
import "@photo-sphere-viewer/core/index.css";

export default function PanoramaViewer({ panoramaUrl, viewState, onViewStateChange }) {
  const containerRef = useRef(null);
  const callbackRef = useRef(onViewStateChange);

  useEffect(() => { callbackRef.current = onViewStateChange; }, [onViewStateChange]);

  useEffect(() => {
    if (!containerRef.current || !panoramaUrl) return undefined;
    const viewer = new Viewer({
      container: containerRef.current,
      panorama: panoramaUrl,
      navbar: false,
      defaultYaw: viewState?.yaw ?? 0,
      defaultPitch: viewState?.pitch ?? 0,
      defaultZoomLvl: viewState?.zoom ?? 35,
      minFov: 35,
      maxFov: 95,
      mousewheelCtrlKey: false,
      touchmoveTwoFingers: false,
      moveSpeed: 1.2,
      zoomSpeed: 1.1,
    });

    const report = () => {
      const position = viewer.getPosition();
      callbackRef.current?.({
        yaw: position.yaw,
        pitch: position.pitch,
        zoom: viewer.getZoomLevel(),
      });
    };
    viewer.addEventListener("position-updated", report);
    viewer.addEventListener("zoom-updated", report);
    return () => viewer.destroy();
  }, [panoramaUrl]);

  return <div ref={containerRef} className="sphere-viewer" aria-label="Draggable 360-degree panorama" />;
}
