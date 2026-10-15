/**
 * Select.tsx — a native <select> styled to match. Native on purpose: it's fully accessible and gets
 * the phone's own picker on mobile.
 */
import clsx from 'clsx';
import { useId, type ReactNode, type SelectHTMLAttributes } from 'react';
import { Field } from './Input';
import s from './ui.module.css';

export function Select({
  label, hint, error, className, id, children, ...rest
}: { label?: ReactNode; hint?: ReactNode; error?: ReactNode } & SelectHTMLAttributes<HTMLSelectElement>) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  return (
    <Field label={label} hint={hint} error={error} id={fieldId}>
      <select id={fieldId} className={clsx(s.select, className)} {...rest}>
        {children}
      </select>
    </Field>
  );
}
