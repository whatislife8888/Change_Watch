/**
 * Loupe.tsx — a watchmaker's magnifier that follows the pointer over a screenshot.
 *
 * - A 220 px circular lens with a knurled steel bezel and a soft vignette, 2.5× zoom
 *   (Alt/Option + scroll changes it between 1.5× and 4×).
 * - Inside the lens is a layer as big as the image × zoom, with the newer screenshot as its background
 *   and the changed regions drawn on it; we slide that layer so the point under the lens centre lines up.
 * - Hold Space (or press and hold on touch) to see the OLDER version inside the lens only — like lifting
 *   the crystal to see what was there before.
 * - The lens glides on a spring (Motion useSpring), and hides when the pointer leaves.
 */
import { motion, useSpring, useTransform } from 'motion/react';
import { useEffect, useRef, useState, type PointerEvent as RPointerEvent } from 'react';
import type { Region } from '../../api/types';
import { usePrefersReducedMotion } from '../../design/motion';
import s from './Loupe.module.css';

const LENS = 220;
const R = LENS / 2;

export function Loupe({ newer, older, naturalWidth, regions }: { newer: string; older?: string; naturalWidth: number; regions: Region[] }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [zoom, setZoom] = useState(2.5);
  const [showOlder, setShowOlder] = useState(false);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const reduced = usePrefersReducedMotion();
  const springCfg = reduced ? { stiffness: 2000, damping: 100 } : { stiffness: 300, damping: 30 };
  // x/y = the point (in displayed-image pixels) the lens is centred on.
  const x = useSpring(0, springCfg);
  const y = useSpring(0, springCfg);
  const holdTimer = useRef<number | undefined>(undefined);

  const scale = size.w ? size.w / naturalWidth : 1;
  const lensX = useTransform(x, (v) => v - R);
  const lensY = useTransform(y, (v) => v - R);
  const layerX = useTransform(x, (v) => R - v * zoom);
  const layerY = useTransform(y, (v) => R - v * zoom);

  // Keep track of the displayed image size (it changes with the window).
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Space = show the older version while held (only while the lens is visible).
  useEffect(() => {
    if (!visible || !older) return;
    const down = (e: KeyboardEvent) => { if (e.code === 'Space') { e.preventDefault(); setShowOlder(true); } };
    const up = (e: KeyboardEvent) => { if (e.code === 'Space') setShowOlder(false); };
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    return () => { window.removeEventListener('keydown', down); window.removeEventListener('keyup', up); };
  }, [visible, older]);

  // Alt/Option + wheel changes zoom. Needs a non-passive listener so we can stop the page scrolling.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.altKey) return;
      e.preventDefault();
      setZoom((z) => Math.min(4, Math.max(1.5, +(z - Math.sign(e.deltaY) * 0.25).toFixed(2))));
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);

  function moveTo(e: RPointerEvent) {
    const rect = wrapRef.current!.getBoundingClientRect();
    x.set(e.clientX - rect.left);
    y.set(e.clientY - rect.top);
  }

  function onPointerDown(e: RPointerEvent) {
    if (e.pointerType !== 'touch') return;
    const rect = wrapRef.current!.getBoundingClientRect();
    x.jump(e.clientX - rect.left);
    y.jump(e.clientY - rect.top);
    setVisible(true);
    (e.target as Element).setPointerCapture?.(e.pointerId);
    window.clearTimeout(holdTimer.current);
    holdTimer.current = window.setTimeout(() => setShowOlder(true), 450);
  }

  function onPointerUp(e: RPointerEvent) {
    if (e.pointerType !== 'touch') return;
    window.clearTimeout(holdTimer.current);
    setShowOlder(false);
    setVisible(false);
  }

  const image = showOlder && older ? older : newer;

  return (
    <div
      ref={wrapRef}
      className={s.wrap}
      onPointerEnter={(e) => { if (e.pointerType !== 'touch') { const r = wrapRef.current!.getBoundingClientRect(); x.jump(e.clientX - r.left); y.jump(e.clientY - r.top); setVisible(true); } }}
      onPointerMove={(e) => { if (visible) moveTo(e); }}
      onPointerLeave={(e) => { if (e.pointerType !== 'touch') { setVisible(false); setShowOlder(false); } }}
      onPointerDown={onPointerDown}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <img src={newer} alt="Newer screenshot with changed areas highlighted" className={s.img} draggable={false} />
      {regions.map((r, i) => (
        <span key={i} className={s.region} style={{ left: r.x * scale, top: r.y * scale, width: r.w * scale, height: r.h * scale }} />
      ))}
      {visible && size.w > 0 && (
        <motion.div className={s.lens} style={{ x: lensX, y: lensY }} aria-hidden="true">
          <motion.div
            className={s.layer}
            style={{ x: layerX, y: layerY, width: size.w * zoom, height: size.h * zoom, backgroundImage: `url(${image})` }}
          >
            {!showOlder && regions.map((r, i) => (
              <span key={i} className={s.regionZoomed}
                style={{ left: r.x * scale * zoom, top: r.y * scale * zoom, width: r.w * scale * zoom, height: r.h * scale * zoom }} />
            ))}
          </motion.div>
          <span className={s.vignette} />
          {showOlder && <span className={s.badge}>Older version</span>}
          <span className={s.zoom}>{zoom.toFixed(1)}×</span>
        </motion.div>
      )}
    </div>
  );
}
