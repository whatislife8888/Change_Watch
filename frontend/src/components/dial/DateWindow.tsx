/**
 * DateWindow.tsx — the small aperture at 3 o'clock showing how long ago the page last changed
 * ("now", "5m", "2h", "3d", "—"), in Zodiak numerals, ink on opaline — like a watch's date window.
 * It's HTML layered over the dial's SVG (positioned in %) so the digits can use the Odometer roll.
 */
import { Odometer } from '../odometer/Odometer';
import s from './Dial.module.css';

export function DateWindow({ text, fontSize }: { text: string; fontSize: number }) {
  return (
    <div className={s.dateWindow} style={{ fontSize }} aria-hidden="true">
      <Odometer value={text} />
    </div>
  );
}
