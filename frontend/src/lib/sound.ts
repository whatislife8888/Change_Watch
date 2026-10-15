/**
 * sound.ts — optional mechanical sounds, synthesised with the Web Audio API (no audio files).
 *
 * - tick(): a soft click when a check finishes (a short burst of filtered noise).
 * - chime(): a two-note chime when a change is detected, like a minute repeater striking:
 *   1318 Hz (E6) then 988 Hz (B5), each fading out exponentially, as a struck gong does.
 *
 * Browsers only allow audio after a user gesture, so the AudioContext is created on the first click of
 * the sound toggle (see `unlockAudio`). Sound is off by default.
 */

let ctx: AudioContext | null = null;
let enabled = false;

export function setSoundEnabled(on: boolean): void {
  enabled = on;
}

/** Create (or resume) the AudioContext. Must be called from a click handler. */
export function unlockAudio(): void {
  try {
    if (!ctx) ctx = new AudioContext();
    if (ctx.state === 'suspended') void ctx.resume();
  } catch {
    ctx = null;
  }
}

/** One struck note: a sine wave whose volume decays exponentially. */
function strike(freq: number, at: number, duration: number, volume: number): void {
  if (!ctx) return;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = 'sine';
  osc.frequency.value = freq;
  gain.gain.setValueAtTime(0.0001, at);
  gain.gain.exponentialRampToValueAtTime(volume, at + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.0001, at + duration);
  osc.connect(gain).connect(ctx.destination);
  osc.start(at);
  osc.stop(at + duration + 0.05);
}

/** Soft mechanical tick: 30 ms of band-passed noise. */
export function tick(): void {
  if (!enabled || !ctx) return;
  const length = Math.floor(ctx.sampleRate * 0.03);
  const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < length; i++) data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / length, 4);
  const src = ctx.createBufferSource();
  src.buffer = buffer;
  const filter = ctx.createBiquadFilter();
  filter.type = 'bandpass';
  filter.frequency.value = 3200;
  filter.Q.value = 4;
  const gain = ctx.createGain();
  gain.gain.value = 0.25;
  src.connect(filter).connect(gain).connect(ctx.destination);
  src.start();
}

/** Two-note chime for a detected change. */
export function chime(): void {
  if (!enabled || !ctx) return;
  const now = ctx.currentTime;
  strike(1318, now, 1.2, 0.12);
  strike(988, now + 0.32, 1.6, 0.12);
}
