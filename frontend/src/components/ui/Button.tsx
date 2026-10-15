/**
 * Button.tsx — the app's buttons. Primary is a fully rounded "crown" in the accent colour; secondary
 * is a hairline outline; ghost is text-only; danger is for destructive actions.
 * ButtonLink renders the same look as a router link (for navigation).
 */
import clsx from 'clsx';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { Link, type LinkProps } from 'react-router-dom';
import s from './ui.module.css';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';

interface CommonProps {
  variant?: Variant;
  size?: 'md' | 'sm';
  iconOnly?: boolean;
  children?: ReactNode;
}

function classes(variant: Variant, size: 'md' | 'sm', iconOnly: boolean, extra?: string) {
  return clsx(s.btn, s[variant], size === 'sm' && s.small, iconOnly && s.iconOnly, extra);
}

/** A <button>. Pass `loading` to disable it while a request runs. */
export function Button({
  variant = 'secondary', size = 'md', iconOnly = false, loading = false, className, children, disabled, type = 'button', ...rest
}: CommonProps & ButtonHTMLAttributes<HTMLButtonElement> & { loading?: boolean }) {
  return (
    <button
      type={type}
      className={classes(variant, size, iconOnly, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {children}
    </button>
  );
}

/** A router <Link> styled as a button. */
export function ButtonLink({ variant = 'secondary', size = 'md', iconOnly = false, className, children, ...rest }: CommonProps & LinkProps) {
  return (
    <Link className={classes(variant, size, iconOnly, className)} {...rest}>
      {children}
    </Link>
  );
}
