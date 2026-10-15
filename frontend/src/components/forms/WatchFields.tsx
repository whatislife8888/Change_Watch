/**
 * WatchFields.tsx — form controls shared by "Add page" and the Page detail "Settings" tab:
 * interval (segmented control + custom), sensitivity (with one-line explanations), keywords + mode.
 */
import { useId, useState } from 'react';
import type { KeywordMode, Sensitivity } from '../../api/types';
import { Input } from '../ui/Input';
import { SegmentedControl } from '../ui/SegmentedControl';
import s from './WatchFields.module.css';

const PRESETS = [15, 30, 60, 180, 360, 720, 1440];
const PRESET_LABELS: Record<number, string> = { 15: '15m', 30: '30m', 60: '1h', 180: '3h', 360: '6h', 720: '12h', 1440: '24h' };

/** Check interval: presets as a segmented control, plus "Custom" (minutes, 15–1440). */
export function IntervalField({ value, onChange }: { value: number; onChange: (minutes: number) => void }) {
  const isPreset = PRESETS.includes(value);
  const [custom, setCustom] = useState(!isPreset);
  const [text, setText] = useState(String(value));
  const id = useId();
  const selected: number | 'custom' = custom ? 'custom' : value;
  const n = Number(text);
  const invalid = custom && (!Number.isInteger(n) || n < 15 || n > 1440);
  return (
    <fieldset className={s.fieldset}>
      <legend className={s.legend}>Check every</legend>
      <SegmentedControl<number | 'custom'>
        label="Check interval"
        value={selected}
        onChange={(v) => {
          if (v === 'custom') {
            setCustom(true);
            setText(String(value));
          } else {
            setCustom(false);
            onChange(v);
          }
        }}
        options={[
          ...PRESETS.map((m) => ({ value: m as number | 'custom', label: PRESET_LABELS[m], ariaLabel: m < 60 ? `${m} minutes` : `${m / 60} hours` })),
          { value: 'custom', label: 'Custom' },
        ]}
      />
      {custom && (
        <div className={s.custom}>
          <Input
            id={id}
            label="Minutes between checks"
            type="number"
            inputMode="numeric"
            min={15}
            max={1440}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              const v = Number(e.target.value);
              if (Number.isInteger(v) && v >= 15 && v <= 1440) onChange(v);
            }}
            error={invalid ? 'Choose an interval between 15 minutes and 24 hours.' : undefined}
            hint="Between 15 (every quarter hour) and 1440 (once a day)."
          />
        </div>
      )}
    </fieldset>
  );
}

const SENS_HELP: Record<Sensitivity, string> = {
  low: 'Only big changes: at least 100 characters and 2% of the page.',
  medium: 'Real edits, not typo fixes: about a sentence or a new line. Recommended.',
  high: 'Any difference at all, even view counters.',
};

export function SensitivityField({ value, onChange }: { value: Sensitivity; onChange: (v: Sensitivity) => void }) {
  return (
    <fieldset className={s.fieldset}>
      <legend className={s.legend}>Sensitivity</legend>
      <SegmentedControl<Sensitivity>
        label="Sensitivity"
        value={value}
        onChange={onChange}
        options={[{ value: 'low', label: 'Low' }, { value: 'medium', label: 'Medium' }, { value: 'high', label: 'High' }]}
      />
      <p className={s.help}>{SENS_HELP[value]}</p>
    </fieldset>
  );
}

const MODE_HELP: Record<KeywordMode, string> = {
  off: 'Alert on any meaningful change.',
  appear: 'Alert only when one of these words newly appears (e.g. "admit card").',
  disappear: 'Alert only when one of these words disappears (e.g. "Sold out").',
  any: 'Alert only when a changed line mentions one of these words.',
};

export function KeywordFields({ text, mode, onText, onMode }: {
  text: string; mode: KeywordMode; onText: (t: string) => void; onMode: (m: KeywordMode) => void;
}) {
  return (
    <div className={s.stack}>
      <fieldset className={s.fieldset}>
        <legend className={s.legend}>Keyword alerts</legend>
        <SegmentedControl<KeywordMode>
          label="Keyword mode"
          value={mode}
          onChange={onMode}
          options={[{ value: 'off', label: 'Off' }, { value: 'appear', label: 'Appears' }, { value: 'disappear', label: 'Disappears' }, { value: 'any', label: 'Mentioned' }]}
        />
        <p className={s.help}>{MODE_HELP[mode]}</p>
      </fieldset>
      {mode !== 'off' && (
        <Input label="Keywords" value={text} onChange={(e) => onText(e.target.value)} placeholder={'"sold out", restock'}
          hint="Separate with commas. Put phrases in quotes. Not case-sensitive. We still save every version." />
      )}
    </div>
  );
}
