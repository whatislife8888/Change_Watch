/**
 * VisualViews.tsx — the three image-based comparison views:
 *   ScreenshotDiff — the newer screenshot with glowing changed regions + the Loupe
 *   SliderCompare  — old and new stacked, a draggable divider reveals one or the other (clip-path)
 *   OverlayCompare — onion skin: the new version over the old with an opacity slider
 * All three live in one scroll frame, so both versions always scroll together.
 */
import { useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import type { CompareResult } from '../../api/types';
import { mediaUrl } from '../../api/client';
import { Loupe } from '../loupe/Loupe';
import s from './Diff.module.css';

type Visual = CompareResult['visual'];

export function ScreenshotDiff({ visual }: { visual: Visual }) {
  const shift = visual.shifted_by_px;
  return (
    <div>
      <p className={s.note}>
        {visual.regions.length === 0
          ? 'The screenshots look the same.'
          : `${visual.changed_percent.toFixed(1)}% of the page looks different.`}
        {shift !== 0 && ` Content moved ${shift > 0 ? 'down' : 'up'} ${Math.abs(shift)} px; we lined the versions up before comparing.`}
      </p>
      <div className={s.shotFrame}>
        <Loupe newer={mediaUrl(visual.after_url)!} older={mediaUrl(visual.before_url)} naturalWidth={visual.width} regions={visual.regions} />
      </div>
      <p className={s.hint}>Hold Space to see the older version under the loupe. Alt (Option) and scroll to zoom. On touch screens, press and hold.</p>
    </div>
  );
}

export function SliderCompare({ visual, labels }: { visual: Visual; labels: [string, string] }) {
  const [pos, setPos] = useState(50);
  const stackRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const setFromPointer = (e: PointerEvent) => {
    const rect = stackRef.current!.getBoundingClientRect();
    setPos(Math.min(100, Math.max(0, ((e.clientX - rect.left) / rect.width) * 100)));
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'ArrowLeft') { e.preventDefault(); setPos((p) => Math.max(0, p - 5)); }
    if (e.key === 'ArrowRight') { e.preventDefault(); setPos((p) => Math.min(100, p + 5)); }
  };

  return (
    <div>
      <div className={s.sliderLabels}><span>{labels[0]}</span><span>{labels[1]}</span></div>
      <div className={s.shotFrame}>
        <div
          ref={stackRef}
          className={s.sliderStack}
          onPointerDown={(e) => { dragging.current = true; (e.target as Element).setPointerCapture?.(e.pointerId); setFromPointer(e); }}
          onPointerMove={(e) => { if (dragging.current) setFromPointer(e); }}
          onPointerUp={() => { dragging.current = false; }}
        >
          <img src={mediaUrl(visual.after_url)} alt="Newer version" className={s.shotImg} draggable={false} />
          {/* The older image sits on top and is clipped to the left part, up to the divider. */}
          <img src={mediaUrl(visual.before_url)} alt="Older version" className={`${s.shotImg} ${s.sliderTop}`} draggable={false}
            style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }} />
          <button type="button" role="slider" aria-label="Divider between older and newer version" aria-valuemin={0} aria-valuemax={100}
            aria-valuenow={Math.round(pos)} className={s.sliderHandle} style={{ left: `${pos}%` }} onKeyDown={onKey} />
        </div>
      </div>
      <p className={s.hint}>Drag the divider, or focus it and use the arrow keys. Older on the left, newer on the right.</p>
    </div>
  );
}

export function OverlayCompare({ visual }: { visual: Visual }) {
  const [opacity, setOpacity] = useState(50);
  return (
    <div>
      <label className={s.overlayControls}>
        <span>Older</span>
        <input type="range" min={0} max={100} value={opacity} onChange={(e) => setOpacity(Number(e.target.value))} aria-label="Newer version opacity" />
        <span>Newer</span>
        <span className="num">{opacity}%</span>
      </label>
      <div className={s.shotFrame}>
        <div className={s.sliderStack}>
          <img src={mediaUrl(visual.before_url)} alt="Older version" className={s.shotImg} draggable={false} />
          <img src={mediaUrl(visual.after_url)} alt="Newer version" className={`${s.shotImg} ${s.sliderTop}`} draggable={false} style={{ opacity: opacity / 100 }} />
        </div>
      </div>
    </div>
  );
}
