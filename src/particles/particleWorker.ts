/**
 * Particle system worker for Little Philosophy.
 *
 * Runs entirely off the main thread using OffscreenCanvas.
 * Particles move through a time-evolving flow field, creating organic motion.
 *
 * Three depth tiers create parallax:
 *   - Background (tiny, slow, dim)
 *   - Midground (medium, normal)
 *   - Accent (large, bright, colored — 5% of pool)
 *
 * Accent particles illuminate nearby non-accent particles,
 * tinting them with the accent's color.
 *
 * Inspired by the Firmament particle system, simplified for this project.
 */

// ===== Tunables ==============================================================

/** Target number of particles on screen. */
const POPULATION = 100;

/** Fraction of particles that are large, bright accents. */
const ACCENT_CHANCE = 0.05;

/** Accent hues — mapped to tile type colors (concept, philosopher, writing). */
const ACCENT_HUES = [197, 36, 122]; // cyan-ish, amber-ish, green-ish

/** Flow field resolution (pixels per grid cell). */
const FLOW_RESOLUTION = 20;

/** How fast the flow field animates. */
const FLOW_SPEED = 0.001;

/** How strongly the flow field steers particles. */
const FLOW_INTENSITY = 0.012;

/** Particle lifecycle in frames. */
const BASE_LIFE = 200;
const LIFE_VARIANCE = 120;
const FADE_FRAMES = 50;

/** Trail settings for accent particles. */
const TRAIL_MAX = 25;
const TRAIL_FADE = 0.93;

/** Illumination: how close an accent must be to light up others. */
const ILLUMINATION_RANGE = 80;
const ILLUMINATION_RANGE_SQ = ILLUMINATION_RANGE * ILLUMINATION_RANGE;

/** Scroll physics. */
const SCROLL_SCALE = 0.003;
const SCROLL_IMPULSE_DECAY = 0.9;
const SCROLL_DAMP = 0.92;
const MAX_SCROLL_VY = 5;

/** Size bounds for depth normalization. */
const MIN_SIZE = 0.5;
const MAX_SIZE = 5;

// ===== Lookup tables for fast trig ==========================================

const LUT_SIZE = 1024;
const sinLUT = new Float32Array(LUT_SIZE);
const cosLUT = new Float32Array(LUT_SIZE);
for (let i = 0; i < LUT_SIZE; i++) {
  const a = (i / LUT_SIZE) * Math.PI * 2;
  sinLUT[i] = Math.sin(a);
  cosLUT[i] = Math.cos(a);
}
function fsin(a: number): number {
  const n = ((a % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
  return sinLUT[Math.floor((n / (Math.PI * 2)) * LUT_SIZE) % LUT_SIZE];
}
function fcos(a: number): number {
  const n = ((a % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
  return cosLUT[Math.floor((n / (Math.PI * 2)) * LUT_SIZE) % LUT_SIZE];
}

// ===== Message handling =====================================================

let system: ParticleSystem | null = null;

self.onmessage = (e: MessageEvent) => {
  const msg = e.data;

  if (msg.canvas) {
    const canvas = msg.canvas as OffscreenCanvas;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    canvas.width = msg.width;
    canvas.height = msg.height;
    ctx.scale(msg.dpr, msg.dpr);
    system = new ParticleSystem(ctx, msg.width / msg.dpr, msg.height / msg.dpr);
    return;
  }

  if (!system) return;

  switch (msg.type) {
    case "scroll":
      system.addScrollImpulse(-msg.dy * SCROLL_SCALE);
      break;
    case "burst":
      system.burst();
      break;
    case "resize":
      // Future: handle resize
      break;
  }
};

// ===== Particle System ======================================================

class ParticleSystem {
  private ctx: OffscreenCanvasRenderingContext2D;
  private w: number;
  private h: number;
  private particles: Particle[] = [];
  private accents: Particle[] = [];
  private flowField: Float32Array;
  private flowCols: number;
  private flowRows: number;
  private time = 0;
  private impulse = 0;

  constructor(ctx: OffscreenCanvasRenderingContext2D, w: number, h: number) {
    this.ctx = ctx;
    this.w = w;
    this.h = h;
    this.flowCols = Math.ceil(w / FLOW_RESOLUTION);
    this.flowRows = Math.ceil(h / FLOW_RESOLUTION);
    this.flowField = new Float32Array(this.flowCols * this.flowRows * 2);
    this.seed(POPULATION);
    this.loop();
  }

  addScrollImpulse(dy: number) {
    this.impulse += dy;
  }

  burst() {
    const cx = this.w / 2;
    const cy = this.h / 2;
    for (const p of this.particles) {
      const dx = p.x - cx;
      const dy = p.y - cy;
      const dist = Math.hypot(dx, dy) || 1;
      const force = 3 + Math.random() * 2;
      p.vx += (dx / dist) * force;
      p.vy += (dy / dist) * force;
    }
  }

  private seed(n: number) {
    for (let i = 0; i < n; i++) {
      this.particles.push(new Particle(this.w, this.h));
    }
  }

  private updateFlowField() {
    let yoff = this.time * FLOW_SPEED;
    for (let row = 0; row < this.flowRows; row++) {
      let xoff = this.time * FLOW_SPEED;
      for (let col = 0; col < this.flowCols; col++) {
        const idx = (row * this.flowCols + col) * 2;
        const angle = fsin(xoff) * fcos(yoff) * Math.PI * 2;
        this.flowField[idx] = fcos(angle);
        this.flowField[idx + 1] = fsin(angle);
        xoff += 0.1;
      }
      yoff += 0.1;
    }
  }

  private loop = () => {
    this.ctx.clearRect(0, 0, this.w, this.h);
    this.time++;
    this.updateFlowField();

    // Distribute scroll impulse
    if (this.impulse !== 0) {
      for (const p of this.particles) p.applyImpulse(this.impulse);
      this.impulse *= SCROLL_IMPULSE_DECAY;
      if (Math.abs(this.impulse) < 0.001) this.impulse = 0;
    }

    // Pre-filter accents for illumination
    this.accents = this.particles.filter((p) => p.isAccent);

    // Update + draw
    this.particles = this.particles.filter((p) => {
      const alive = p.update(this.flowField, this.flowCols, this.w, this.h);
      if (alive) {
        if (!p.isAccent && this.accents.length > 0) {
          p.computeIllumination(this.accents);
        }
        p.draw(this.ctx);
      }
      return alive;
    });

    // Replenish
    if (this.particles.length < POPULATION && this.time % 2 === 0) {
      this.particles.push(new Particle(this.w, this.h));
    }

    self.requestAnimationFrame(this.loop);
  };
}

// ===== Particle =============================================================

class Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  private scrollVy = 0;

  readonly isAccent: boolean;
  private size: number;
  private sizeNorm: number;
  private hue: number;
  private baseAlpha: number;
  private speedFactor: number;

  private life = 0;
  private maxLife: number;

  private trail: { x: number; y: number; a: number }[] = [];

  // Illumination state (set each frame for non-accents)
  private illumAlpha = 0;
  private illumHue: number;

  constructor(w: number, h: number) {
    this.x = Math.random() * w;
    this.y = Math.random() * h;
    this.vx = (Math.random() - 0.5) * 0.8;
    this.vy = (Math.random() - 0.5) * 0.8;

    this.isAccent = Math.random() < ACCENT_CHANCE;

    // --- Size by depth tier ---
    if (this.isAccent) {
      this.size = 3 + Math.pow(Math.random(), 0.3) * 2; // 3–5
    } else if (Math.random() < 0.3) {
      // Background
      this.size = MIN_SIZE + Math.random() * 0.5; // 0.5–1
    } else {
      // Midground
      this.size = 1.5 + Math.pow(Math.random(), 0.5) * 2; // 1.5–3.5
    }
    this.sizeNorm = (this.size - MIN_SIZE) / (MAX_SIZE - MIN_SIZE);

    // --- Color ---
    if (this.isAccent) {
      this.hue = ACCENT_HUES[Math.floor(Math.random() * ACCENT_HUES.length)];
      this.maxLife = (BASE_LIFE + Math.random() * LIFE_VARIANCE) * 1.5;
    } else {
      this.hue = 200 + Math.random() * 40; // blue-ish
      this.maxLife = BASE_LIFE + Math.random() * LIFE_VARIANCE;
    }
    this.illumHue = this.hue;

    // --- Alpha by tier ---
    const eased = Math.pow(this.sizeNorm, 2.5);
    if (this.isAccent) {
      this.baseAlpha = 0.5 + eased * 0.5;
    } else if (this.size < 1.2) {
      this.baseAlpha = 0.03 + eased * 0.15;
    } else {
      this.baseAlpha = 0.08 + eased * 0.4;
    }

    this.speedFactor = (0.8 + this.sizeNorm * 0.2) * (this.isAccent ? 2 : 1);
  }

  applyImpulse(dy: number) {
    const mul = this.isAccent ? 1 : 1.5;
    this.scrollVy += dy * this.sizeNorm * mul;
    this.scrollVy = Math.max(-MAX_SCROLL_VY, Math.min(MAX_SCROLL_VY, this.scrollVy));
  }

  computeIllumination(accents: Particle[]) {
    this.illumAlpha = 0;
    this.illumHue = this.hue;

    let totalIllum = 0;
    let weightedHue = 0;
    let totalWeight = 0;

    for (const a of accents) {
      const dx = a.x - this.x;
      const dy = a.y - this.y;
      const dSq = dx * dx + dy * dy;
      if (dSq >= ILLUMINATION_RANGE_SQ) continue;

      const dist = Math.sqrt(dSq);
      const falloff = 1 - dist / ILLUMINATION_RANGE;
      const strength = falloff * falloff * (a.size / MAX_SIZE) * (0.5 + this.sizeNorm * 0.5) * 0.7;

      totalIllum += strength;
      weightedHue += a.hue * strength;
      totalWeight += strength;

      if (totalIllum >= 0.8) break; // already saturated
    }

    const cap = 0.8 * (0.5 + this.sizeNorm * 0.5);
    this.illumAlpha = Math.min(totalIllum, cap);

    if (totalWeight > 0) {
      const blend = Math.min(totalIllum * 2, cap);
      this.illumHue = this.hue * (1 - blend) + (weightedHue / totalWeight) * blend;
    }
  }

  update(field: Float32Array, cols: number, maxX: number, maxY: number): boolean {
    this.life++;
    this.scrollVy *= SCROLL_DAMP * this.sizeNorm;

    // Flow field influence
    const col = Math.floor(this.x / FLOW_RESOLUTION);
    const row = Math.floor(this.y / FLOW_RESOLUTION);
    const idx = (row * cols + col) * 2;
    if (field[idx] !== undefined) {
      const perspScale = 0.2 + this.sizeNorm * 0.6;
      const fScale = FLOW_INTENSITY * this.speedFactor * perspScale;
      this.vx += field[idx] * fScale;
      this.vy += field[idx + 1] * fScale;
    }

    // Wobble
    const ang = Math.atan2(this.vy, this.vx) + fsin(this.life * 0.05) * 0.05;
    const spd = Math.hypot(this.vx, this.vy);
    this.vx = fcos(ang) * spd;
    this.vy = fsin(ang) * spd;

    // Move
    const movScale = 0.2 + this.sizeNorm * 0.6;
    this.x += this.vx * movScale;
    this.y += this.vy * movScale + this.scrollVy;

    // Kill if off-screen
    if (this.life <= this.maxLife) {
      if (this.x < 0 || this.x > maxX || this.y < 0 || this.y > maxY) {
        this.life = this.maxLife;
      }
    }

    // Trail (accents only)
    if (this.isAccent) {
      this.trail.unshift({ x: this.x, y: this.y, a: 1 });
      for (const t of this.trail) t.a *= TRAIL_FADE;
      if (this.trail.length > TRAIL_MAX) this.trail.pop();
    }

    return this.life < this.maxLife + FADE_FRAMES;
  }

  draw(ctx: OffscreenCanvasRenderingContext2D) {
    const phase = this.phaseAlpha();
    if (phase <= 0) return;

    if (this.isAccent) {
      // Twinkle
      const twinkle = 1 + 0.3 * fsin(this.life * 0.1 + this.hue);
      const alpha = phase * twinkle;

      // Glow
      const glowR = this.size * 6;
      const grad = ctx.createRadialGradient(this.x, this.y, 0, this.x, this.y, glowR);
      grad.addColorStop(0, `hsla(${this.hue},100%,70%,${alpha * 0.15})`);
      grad.addColorStop(1, `hsla(${this.hue},100%,70%,0)`);
      ctx.beginPath();
      ctx.fillStyle = grad;
      ctx.arc(this.x, this.y, glowR, 0, Math.PI * 2);
      ctx.fill();

      // Trail
      if (this.trail.length > 1) {
        ctx.lineWidth = this.size * 0.8;
        ctx.beginPath();
        ctx.moveTo(this.trail[0].x, this.trail[0].y);
        for (let i = 1; i < this.trail.length; i++) {
          const segAlpha = Math.min(this.trail[i - 1].a, this.trail[i].a) * phase;
          if (segAlpha < 0.02) break;
          ctx.lineTo(this.trail[i].x, this.trail[i].y);
        }
        ctx.strokeStyle = `hsla(${this.hue},100%,70%,${phase * 0.3})`;
        ctx.stroke();
      }

      // Core
      ctx.beginPath();
      ctx.fillStyle = `hsla(${this.hue},100%,70%,${alpha})`;
      ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
      ctx.fill();
    } else {
      // Non-accent: illumination blending
      const illumFade = phase / this.baseAlpha;
      const fadedIllum = this.illumAlpha * illumFade;
      const finalAlpha = phase + fadedIllum;
      const sat = fadedIllum > 0.02 ? 100 : 60;
      ctx.beginPath();
      ctx.fillStyle = `hsla(${this.illumHue},${sat}%,70%,${finalAlpha})`;
      ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  private phaseAlpha(): number {
    if (this.life < FADE_FRAMES) {
      return (this.life / FADE_FRAMES) * this.baseAlpha;
    }
    if (this.life <= this.maxLife) {
      return this.baseAlpha;
    }
    return Math.max(0, 1 - (this.life - this.maxLife) / FADE_FRAMES) * this.baseAlpha;
  }
}
