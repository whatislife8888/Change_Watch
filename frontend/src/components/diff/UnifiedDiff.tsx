/**
 * UnifiedDiff.tsx — the text diff as one column: added lines on a lume tint, removed lines on a ruby tint
 * with strikethrough, word-level highlights inside edited lines, and long unchanged runs collapsed
 * ("Show 23 unchanged lines").
 *
 * The backend sends structured `ops` (equal / insert / delete / replace-with-word-pairs); this component
 * only decides how to draw them.
 */
import { useState, type ReactNode } from 'react';
import type { DiffOp } from '../../api/types';
import s from './Diff.module.css';

const CONTEXT = 3;

/** Word segments of one side of an edited line, with the changed words highlighted. */
export function Segments({ parts, side }: { parts: string[][]; side: 'old' | 'new' }) {
  return (
    <>
      {parts.map(([tag, text], i) => {
        if (tag === 'equal') return <span key={i}>{text}</span>;
        if (side === 'old' && tag === 'delete') return <del key={i} className={s.wordDel}>{text}</del>;
        if (side === 'new' && tag === 'insert') return <ins key={i} className={s.wordIns}>{text}</ins>;
        return null;
      })}
    </>
  );
}

/** A run of unchanged lines, collapsed to its first and last few lines with an expand button. */
export function EqualRun({ lines, render, first, last }: { lines: string[]; render: (line: string, key: number) => ReactNode; first: boolean; last: boolean }) {
  const [open, setOpen] = useState(false);
  const head = first ? 0 : CONTEXT;
  const tail = last ? 0 : CONTEXT;
  if (open || lines.length <= head + tail + 2) return <>{lines.map((l, i) => render(l, i))}</>;
  const hidden = lines.length - head - tail;
  return (
    <>
      {lines.slice(0, head).map((l, i) => render(l, i))}
      <button type="button" className={s.collapse} onClick={() => setOpen(true)}>
        Show {hidden} unchanged line{hidden === 1 ? '' : 's'}
      </button>
      {lines.slice(lines.length - tail).map((l, i) => render(l, lines.length - tail + i))}
    </>
  );
}

export function UnifiedDiff({ ops }: { ops: DiffOp[] }) {
  if (ops.every((op) => op.type === 'equal')) {
    return <p className={s.same}>The text of these two versions is the same once noise like timestamps is ignored.</p>;
  }
  return (
    <div className={s.unified} role="table" aria-label="Text differences">
      {ops.map((op, i) => {
        if (op.type === 'equal') {
          return (
            <EqualRun key={i} lines={op.lines ?? []} first={i === 0} last={i === ops.length - 1}
              render={(l, k) => <div key={k} className={s.line} role="row"><span className={s.sign} aria-hidden="true" /><span>{l || ' '}</span></div>} />
          );
        }
        if (op.type === 'insert') {
          return (op.lines ?? []).map((l, k) => (
            <div key={`${i}-${k}`} className={`${s.line} ${s.added}`} role="row"><span className={s.sign} aria-label="added">+</span><span>{l}</span></div>
          ));
        }
        if (op.type === 'delete') {
          return (op.lines ?? []).map((l, k) => (
            <div key={`${i}-${k}`} className={`${s.line} ${s.removed}`} role="row"><span className={s.sign} aria-label="removed">&minus;</span><del>{l}</del></div>
          ));
        }
        return (op.pairs ?? []).map((pair, k) => (
          <div key={`${i}-${k}`} className={s.pair}>
            <div className={`${s.line} ${s.removed}`} role="row"><span className={s.sign} aria-label="before">&minus;</span><span><Segments parts={pair.old} side="old" /></span></div>
            <div className={`${s.line} ${s.added}`} role="row"><span className={s.sign} aria-label="after">+</span><span><Segments parts={pair.new} side="new" /></span></div>
          </div>
        ));
      })}
    </div>
  );
}
