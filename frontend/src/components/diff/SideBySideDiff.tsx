/**
 * SideBySideDiff.tsx — old version on the left, new on the right, aligned row by row, with the same
 * highlights and collapsing as the unified view. Inserted lines leave an empty cell on the left;
 * deleted lines leave one on the right, so matching text always sits on the same row.
 */
import type { DiffOp } from '../../api/types';
import s from './Diff.module.css';
import { EqualRun, Segments } from './UnifiedDiff';

export function SideBySideDiff({ ops, labels }: { ops: DiffOp[]; labels: [string, string] }) {
  return (
    <div className={s.sbs} role="table" aria-label="Side by side differences">
      <div className={s.sbsHead} role="row">
        <span role="columnheader">{labels[0]}</span>
        <span role="columnheader">{labels[1]}</span>
      </div>
      {ops.map((op, i) => {
        if (op.type === 'equal') {
          return (
            <EqualRun key={i} lines={op.lines ?? []} first={i === 0} last={i === ops.length - 1}
              render={(l, k) => (
                <div key={k} className={s.sbsRow} role="row"><span className={s.cell}>{l || ' '}</span><span className={s.cell}>{l || ' '}</span></div>
              )} />
          );
        }
        if (op.type === 'insert') {
          return (op.lines ?? []).map((l, k) => (
            <div key={`${i}-${k}`} className={s.sbsRow} role="row"><span className={`${s.cell} ${s.empty}`} /><span className={`${s.cell} ${s.added}`}>{l}</span></div>
          ));
        }
        if (op.type === 'delete') {
          return (op.lines ?? []).map((l, k) => (
            <div key={`${i}-${k}`} className={s.sbsRow} role="row"><span className={`${s.cell} ${s.removed}`}><del>{l}</del></span><span className={`${s.cell} ${s.empty}`} /></div>
          ));
        }
        return (op.pairs ?? []).map((pair, k) => (
          <div key={`${i}-${k}`} className={s.sbsRow} role="row">
            <span className={`${s.cell} ${s.removedSoft}`}><Segments parts={pair.old} side="old" /></span>
            <span className={`${s.cell} ${s.addedSoft}`}><Segments parts={pair.new} side="new" /></span>
          </div>
        ));
      })}
    </div>
  );
}
