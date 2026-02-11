/**
 * ParticleCanvas — renders the particle system behind the app UI.
 *
 * Uses OffscreenCanvas + Web Worker so particles never block the main thread.
 * Falls back gracefully if OffscreenCanvas isn't supported (just no particles).
 *
 * Props:
 *  - onWorkerReady: callback that receives a ref to the worker so the parent
 *    can send "burst" messages on discovery events.
 */

import { useEffect, useRef, useCallback } from "react";

export interface ParticleWorkerHandle {
  burst(): void;
}

interface ParticleCanvasProps {
  onWorkerReady?: (handle: ParticleWorkerHandle) => void;
}

export default function ParticleCanvas({ onWorkerReady }: ParticleCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const transferred = useRef(false);
  const workerRef = useRef<Worker | null>(null);

  // Scroll handler — forward wheel events to the worker
  const handleWheel = useCallback((e: WheelEvent) => {
    workerRef.current?.postMessage({ type: "scroll", dy: e.deltaY });
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || typeof OffscreenCanvas === "undefined") return;
    if (transferred.current) return;
    transferred.current = true;

    try {
      const dpr = window.devicePixelRatio || 1;
      const width = window.innerWidth * dpr;
      const height = window.innerHeight * dpr;

      const offscreen = canvas.transferControlToOffscreen();
      const worker = new Worker(
        new URL("./particleWorker.ts", import.meta.url),
        { type: "module" }
      );
      workerRef.current = worker;

      worker.postMessage(
        { canvas: offscreen, width, height, dpr },
        [offscreen]
      );

      // Expose burst control to parent
      onWorkerReady?.({
        burst() {
          worker.postMessage({ type: "burst" });
        },
      });
    } catch (err) {
      console.warn("Particle system init failed:", err);
    }

    // Listen for scroll
    window.addEventListener("wheel", handleWheel, { passive: true });

    return () => {
      window.removeEventListener("wheel", handleWheel);
      workerRef.current?.terminate();
      workerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: "fixed",
        inset: 0,
        width: "100vw",
        height: "100vh",
        zIndex: -1,
        pointerEvents: "none",
      }}
    />
  );
}
