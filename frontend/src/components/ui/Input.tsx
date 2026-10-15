/**
 * Input.tsx — form fields with a label, an optional hint and an error message, all wired up for
 * screen readers (aria-describedby / aria-invalid). Also: Checkbox and Switch.
 */
import clsx from 'clsx';
import { forwardRef, useId, type InputHTMLAttributes, type ReactNode } from 'react';
import s from './ui.module.css';

interface FieldProps {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
}

/** Wraps any control with label + hint + error. `children` receives the generated ids. */
export function Field({ label, hint, error, id, children }: FieldProps & { id: string; children: ReactNode }) {
  return (
    <div className={s.field}>
      {label && <label className={s.label} htmlFor={id}>{label}</label>}
      {children}
      {hint && !error && <span id={`${id}-hint`} className={s.hint}>{hint}</span>}
      {error && <span id={`${id}-error`} className={s.error} role="alert">{error}</span>}
    </div>
  );
}

/** A text input with label, hint and error. */
export const Input = forwardRef<HTMLInputElement, FieldProps & InputHTMLAttributes<HTMLInputElement>>(
  function Input({ label, hint, error, className, id, ...rest }, ref) {
    const autoId = useId();
    const fieldId = id ?? autoId;
    return (
      <Field label={label} hint={hint} error={error} id={fieldId}>
        <input
          ref={ref}
          id={fieldId}
          className={clsx(s.input, error && s.invalid, className)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${fieldId}-error` : hint ? `${fieldId}-hint` : undefined}
          {...rest}
        />
      </Field>
    );
  },
);

/** A checkbox with its label text to the right. */
export function Checkbox({ label, hint, ...rest }: { label: ReactNode; hint?: ReactNode } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className={s.checkboxRow}>
      <input type="checkbox" className={s.checkbox} {...rest} />
      <span>
        <span>{label}</span>
        {hint && <span className={s.hint} style={{ display: 'block' }}>{hint}</span>}
      </span>
    </label>
  );
}

/** An on/off switch (a checkbox with role="switch"). */
export function Switch({ label, hint, ...rest }: { label: ReactNode; hint?: ReactNode } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className={s.checkboxRow} style={{ alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
      <span>
        <span>{label}</span>
        {hint && <span className={s.hint} style={{ display: 'block' }}>{hint}</span>}
      </span>
      <input type="checkbox" role="switch" className={s.switch} {...rest} />
    </label>
  );
}
