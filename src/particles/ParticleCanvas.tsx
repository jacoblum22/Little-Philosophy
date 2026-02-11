/**
 * ParticleCanvas — renders the particle system behind the app UI.
 *
 * Uses a regular canvas on the main thread with requestAnimationFrame.
 * 100 particles at ~60fps is well within budget (<1ms per frame).
 *
 * Props:
 *  - onWorkerReady: callback that receives a handle to trigger burst effects.
 */

import { useEffect, useRef, useState } from "react";

/** Handle exposed by ParticleCanvas so the parent can trigger visual effects. */
export interface ParticleHandle {
  /** Trigger a radial burst that pushes all particles outward from the center. */
  burst(): void;
}

interface ParticleCanvasProps {
  onReady?: (handle: ParticleHandle) => void;
}

// ===== Tunables ==============================================================
const POPULATION = 100;
const ACCENT_CHANCE = 0.05;
const ACCENT_HUES = [197, 36, 122]; // cyan, amber, green — matching tile types
const FLOW_RESOLUTION = 20;
const FLOW_SPEED = 0.001;
const FLOW_INTENSITY = 0.012;
const BASE_LIFE = 200;
const LIFE_VARIANCE = 120;
const FADE_FRAMES = 50;
const TRAIL_MAX = 25;
const TRAIL_FADE = 0.93;
const ILLUMINATION_RANGE = 80;
const ILLUMINATION_RANGE_SQ = ILLUMINATION_RANGE * ILLUMINATION_RANGE;
const MIN_SIZE = 0.5;
const MAX_SIZE = 5;

// ===== Lookup tables =========================================================
const LN = 1024;
const sinL = new Float32Array(LN);
const cosL = new Float32Array(LN);
for (let i = 0; i < LN; i++) {
  const a = (i / LN) * Math.PI * 2;
  sinL[i] = Math.sin(a);
  cosL[i] = Math.cos(a);
}
function fsin(a: number) {
  const n = ((a % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
  return sinL[Math.floor((n / (Math.PI * 2)) * LN) % LN];
}
function fcos(a: number) {
  const n = ((a % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
  return cosL[Math.floor((n / (Math.PI * 2)) * LN) % LN];
}

// ===== Particle ==============================================================
class Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  private scrollVy = 0;
  readonly isAccent: boolean;
  readonly size: number;
  private sizeNorm: number;
  readonly hue: number;
  private baseAlpha: number;
  private speedFactor: number;
  private life = 0;
  private maxLife: number;
  private trail: { x: number; y: number; a: number }[] = [];
  private illumAlpha = 0;
  private illumHue: number;

  constructor(w: number, h: number) {
    this.x = Math.random() * w;
    this.y = Math.random() * h;
    this.vx = (Math.random() - 0.5) * 0.8;
    this.vy = (Math.random() - 0.5) * 0.8;
    this.isAccent = Math.random() < ACCENT_CHANCE;

    if (this.isAccent) {
      this.size = 3 + Math.pow(Math.random(), 0.3) * 2;
    } else if (Math.random() < 0.3) {
      this.size = MIN_SIZE + Math.random() * 0.5;
    } else {
      this.size = 1.5 + Math.pow(Math.random(), 0.5) * 2;
    }
    this.sizeNorm = (this.size - MIN_SIZE) / (MAX_SIZE - MIN_SIZE);

    if (this.isAccent) {
      this.hue = ACCENT_HUES[Math.floor(Math.random() * ACCENT_HUES.length)];
      this.maxLife = (BASE_LIFE + Math.random() * LIFE_VARIANCE) * 1.5;
    } else {
      this.hue = 200 + Math.random() * 40;
      this.maxLife = BASE_LIFE + Math.random() * LIFE_VARIANCE;
    }
    this.illumHue = this.hue;

    const eased = Math.pow(this.sizeNorm, 2.5);
    if (this.isAccent) this.baseAlpha = 0.5 + eased * 0.5;
    else if (this.size < 1.2) this.baseAlpha = 0.03 + eased * 0.15;
    else this.baseAlpha = 0.08 + eased * 0.4;

    this.speedFactor = (0.8 + this.sizeNorm * 0.2) * (this.isAccent ? 2 : 1);
  }

  applyImpulse(dy: number) {
    this.scrollVy += dy * this.sizeNorm * (this.isAccent ? 1 : 1.5);
    this.scrollVy = Math.max(-5, Math.min(5, this.scrollVy));
  }

  computeIllumination(accents: Particle[]) {
    this.illumAlpha = 0;
    this.illumHue = this.hue;
    let totalIllum = 0, wHue = 0, wTotal = 0;
    for (const a of accents) {
      const dx = a.x - this.x, dy = a.y - this.y;
      const dSq = dx * dx + dy * dy;
      if (dSq >= ILLUMINATION_RANGE_SQ) continue;
      const dist = Math.sqrt(dSq);
      const f = 1 - dist / ILLUMINATION_RANGE;
      const s = f * f * (a.size / MAX_SIZE) * (0.5 + this.sizeNorm * 0.5) * 0.7;
      totalIllum += s; wHue += a.hue * s; wTotal += s;
      if (totalIllum >= 0.8) break;
    }
    const cap = 0.8 * (0.5 + this.sizeNorm * 0.5);
    this.illumAlpha = Math.min(totalIllum, cap);
    if (wTotal > 0) {
      const blend = Math.min(totalIllum * 2, cap);
      this.illumHue = this.hue * (1 - blend) + (wHue / wTotal) * blend;
    }
  }

  update(field: Float32Array, cols: number, maxX: number, maxY: number): boolean {
    this.life++;
    this.scrollVy *= 0.92 * this.sizeNorm;
    const col = Math.floor(this.x / FLOW_RESOLUTION);
    const row = Math.floor(this.y / FLOW_RESOLUTION);
    const idx = (row * cols + col) * 2;
    if (field[idx] !== undefined) {
      const ps = 0.2 + this.sizeNorm * 0.6;
      const fs = FLOW_INTENSITY * this.speedFactor * ps;
      this.vx += field[idx] * fs;
      this.vy += field[idx + 1] * fs;
    }
    const ang = Math.atan2(this.vy, this.vx) + fsin(this.life * 0.05) * 0.05;
    const spd = Math.hypot(this.vx, this.vy);
    this.vx = fcos(ang) * spd;
    this.vy = fsin(ang) * spd;
    const ms = 0.2 + this.sizeNorm * 0.6;
    this.x += this.vx * ms;
    this.y += this.vy * ms + this.scrollVy;
    if (this.life <= this.maxLife && (this.x < 0 || this.x > maxX || this.y < 0 || this.y > maxY))
      this.life = this.maxLife;
    if (this.isAccent) {
      this.trail.unshift({ x: this.x, y: this.y, a: 1 });
      for (const t of this.trail) t.a *= TRAIL_FADE;
      if (this.trail.length > TRAIL_MAX) this.trail.pop();
    }
    return this.life < this.maxLife + FADE_FRAMES;
  }

  draw(ctx: CanvasRenderingContext2D) {
    const phase = this.phaseAlpha();
    if (phase <= 0) return;
    if (this.isAccent) {
      const tw = 1 + 0.3 * fsin(this.life * 0.1 + this.hue);
      const alpha = phase * tw;
      const glowR = this.size * 6;
      const grad = ctx.createRadialGradient(this.x, this.y, 0, this.x, this.y, glowR);
      grad.addColorStop(0, `hsla(${this.hue},100%,70%,${alpha * 0.15})`);
      grad.addColorStop(1, `hsla(${this.hue},100%,70%,0)`);
      ctx.beginPath(); ctx.fillStyle = grad;
      ctx.arc(this.x, this.y, glowR, 0, Math.PI * 2); ctx.fill();
      if (this.trail.length > 1) {
        ctx.lineWidth = this.size * 0.8;
        ctx.beginPath(); ctx.moveTo(this.trail[0].x, this.trail[0].y);
        for (let i = 1; i < this.trail.length; i++) {
          if (Math.min(this.trail[i - 1].a, this.trail[i].a) * phase < 0.02) break;
          ctx.lineTo(this.trail[i].x, this.trail[i].y);
        }
        ctx.strokeStyle = `hsla(${this.hue},100%,70%,${phase * 0.3})`; ctx.stroke();
      }
      ctx.beginPath(); ctx.fillStyle = `hsla(${this.hue},100%,70%,${alpha})`;
      ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2); ctx.fill();
    } else {
      const iFade = phase / this.baseAlpha;
      const fIllum = this.illumAlpha * iFade;
      const sat = fIllum > 0.02 ? 100 : 60;
      ctx.beginPath();
      ctx.fillStyle = `hsla(${this.illumHue},${sat}%,70%,${phase + fIllum})`;
      ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2); ctx.fill();
    }
  }

  private phaseAlpha(): number {
    if (this.life < FADE_FRAMES) return (this.life / FADE_FRAMES) * this.baseAlpha;
    if (this.life <= this.maxLife) return this.baseAlpha;
    return Math.max(0, 1 - (this.life - this.maxLife) / FADE_FRAMES) * this.baseAlpha;
  }
}

// ===== React Component =======================================================

/**
 * Mutable state bag for the animation loop.
 * Held outside React's render cycle so the loop can read/write without
 * triggering re-renders. A fresh bag is created on every mount.
 */
interface LoopState {
  w: number;
  h: number;
  flowCols: number;
  flowRows: number;
  flowField: Float32Array;
  particles: Particle[];
  time: number;
  impulse: number;
}

/** Build (or rebuild) the mutable state bag for a given canvas size. */
function createLoopState(w: number, h: number): LoopState {
  const flowCols = Math.ceil(w / FLOW_RESOLUTION);
  const flowRows = Math.ceil(h / FLOW_RESOLUTION);
  const particles: Particle[] = [];
  for (let i = 0; i < POPULATION; i++) particles.push(new Particle(w, h));
  return {
    w, h, flowCols, flowRows,
    flowField: new Float32Array(flowCols * flowRows * 2),
    particles,
    time: 0,
    impulse: 0,
  };
}

export default function ParticleCanvas({ onReady }: ParticleCanvasProps) {
  // A key that increments on every mount forces React to create a fresh
  // <canvas> DOM element, sidestepping Strict Mode's setup→cleanup→setup
  // cycle which would otherwise leave a stale canvas reference.
  const [mountKey, setMountKey] = useState(0);

  return <ParticleCanvasInner key={mountKey} onReady={onReady} setMountKey={setMountKey} />;
}

/**
 * Inner component that owns the actual <canvas> element.
 * Each mount gets a brand-new canvas (via the parent's key prop) so
 * getContext("2d") always succeeds, even after Strict Mode cleanup.
 */
function ParticleCanvasInner({
  onReady,
  setMountKey,
}: ParticleCanvasProps & { setMountKey: React.Dispatch<React.SetStateAction<number>> }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef(0);
  const burstRef = useRef<(() => void) | null>(null);
  const loopRef = useRef<LoopState | null>(null);

  useEffect(() => {
    // ----- reduced-motion handling -----
    const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");

    // Listen for runtime changes BEFORE the early return so that toggling
    // reduced-motion OFF triggers a remount even if we started with it ON.
    const onMotionChange = (e: MediaQueryListEvent) => {
      if (e.matches) {
        // User just turned on reduced-motion — stop the loop
        cancelAnimationFrame(animRef.current);
        loopRef.current = null;
      } else {
        // User turned it back off — remount with a fresh canvas
        setMountKey((k) => k + 1);
      }
    };
    motionQuery.addEventListener("change", onMotionChange);

    if (motionQuery.matches) {
      // Don't start the animation loop at all — CSS hides the canvas anyway.
      // The change listener above is still registered so a toggle-off will remount.
      return () => {
        motionQuery.removeEventListener("change", onMotionChange);
      };
    }

    const canvas = canvasRef.current;
    if (!canvas) {
      return () => { motionQuery.removeEventListener("change", onMotionChange); };
    }
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return () => { motionQuery.removeEventListener("change", onMotionChange); };
    }

    // ----- size the backing buffer to match CSS layout -----
    const applySize = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.offsetWidth;
      const h = canvas.offsetHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); // reset + apply fresh scale
      return { w, h };
    };

    const { w, h } = applySize();
    const loop = createLoopState(w, h);
    loopRef.current = loop;

    // ----- burst handle -----
    burstRef.current = () => {
      const ls = loopRef.current;
      if (!ls) return;
      const cx = ls.w / 2, cy = ls.h / 2;
      for (const p of ls.particles) {
        const dx = p.x - cx, dy = p.y - cy;
        const dist = Math.hypot(dx, dy) || 1;
        const force = 3 + Math.random() * 2;
        p.vx += (dx / dist) * force;
        p.vy += (dy / dist) * force;
      }
    };
    onReady?.({ burst() { burstRef.current?.(); } });

    // ----- scroll impulse -----
    const onWheel = (e: WheelEvent) => {
      if (loopRef.current) loopRef.current.impulse += -e.deltaY * 0.003;
    };
    window.addEventListener("wheel", onWheel, { passive: true });

    // ----- resize handling -----
    const ro = new ResizeObserver(() => {
      const { w: nw, h: nh } = applySize();
      const ls = loopRef.current;
      if (!ls) return;
      ls.w = nw;
      ls.h = nh;
      ls.flowCols = Math.ceil(nw / FLOW_RESOLUTION);
      ls.flowRows = Math.ceil(nh / FLOW_RESOLUTION);
      ls.flowField = new Float32Array(ls.flowCols * ls.flowRows * 2);
    });
    ro.observe(canvas);

    // ----- animation loop -----
    const tick = () => {
      const ls = loopRef.current;
      if (!ls) return;
      ctx.clearRect(0, 0, ls.w, ls.h);
      ls.time++;

      // Flow field
      let yoff = ls.time * FLOW_SPEED;
      for (let row = 0; row < ls.flowRows; row++) {
        let xoff = ls.time * FLOW_SPEED;
        for (let col = 0; col < ls.flowCols; col++) {
          const idx = (row * ls.flowCols + col) * 2;
          const angle = fsin(xoff) * fcos(yoff) * Math.PI * 2;
          ls.flowField[idx] = fcos(angle);
          ls.flowField[idx + 1] = fsin(angle);
          xoff += 0.1;
        }
        yoff += 0.1;
      }

      // Scroll impulse
      if (ls.impulse !== 0) {
        for (const p of ls.particles) p.applyImpulse(ls.impulse);
        ls.impulse *= 0.9;
        if (Math.abs(ls.impulse) < 0.001) ls.impulse = 0;
      }

      const accents = ls.particles.filter((p) => p.isAccent);

      ls.particles = ls.particles.filter((p) => {
        const alive = p.update(ls.flowField, ls.flowCols, ls.w, ls.h);
        if (alive) {
          if (!p.isAccent && accents.length > 0) p.computeIllumination(accents);
          p.draw(ctx);
        }
        return alive;
      });

      if (ls.particles.length < POPULATION && ls.time % 2 === 0)
        ls.particles.push(new Particle(ls.w, ls.h));

      animRef.current = requestAnimationFrame(tick);
    };

    animRef.current = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(animRef.current);
      window.removeEventListener("wheel", onWheel);
      ro.disconnect();
      motionQuery.removeEventListener("change", onMotionChange);
      loopRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="particle-canvas"
      style={{
        width: "100%",
        height: "100%",
        pointerEvents: "none",
      }}
    />
  );
}
