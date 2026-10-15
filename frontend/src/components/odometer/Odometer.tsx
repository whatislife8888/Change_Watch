/**
 * Odometer.tsx — numbers that roll digit by digit, like the date wheel behind a watch's date window.
 *
 * How it works: each digit is a narrow window (overflow: hidden, 1em tall) showing one cell of a
 * vertical strip "0 1 2 ... 9". To show digit d we slide the strip up by d cells (translateY(-d*10%)).
 * When the value changes, CSS transitions the slide, so the digits roll. Non-digit characters
 * (commas, ₹, %, letters) are shown as-is. Tabular figures keep every digit the same width, so nothing
 * shifts sideways while rolling. With reduced motion the transition is removed (instant swap).
 */
import type { CSSProperties } from 'react';
import s from './Odometer.module.css';

const DIGITS = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9'];

export function Odometer({ value, className, style, label }: { value: string | number; className?: string; style?: CSSProperties; label?: string }) {
  const text = String(value);
  const chars = text.split('');
  return (
    <span className={`${s.odometer} ${className ?? ''}`} style={style} aria-label={label ?? text} role="text">
      {chars.map((ch, i) => {
        // Key by position from the right so units stay units when the number grows (9 -> 10).
        const key = chars.length - i;
        if (!/\d/.test(ch)) {
          return <span key={`c${key}`} className={s.static} aria-hidden="true">{ch}</span>;
        }
        const d = Number(ch);
        return (
          <span key={`d${key}`} className={s.window} aria-hidden="true">
            <span className={s.strip} style={{ transform: `translateY(${-d * 10}%)` }}>
              {DIGITS.map((n) => <span key={n} className={s.cell}>{n}</span>)}
            </span>
          </span>
        );
      })}
    </span>
  );
}
