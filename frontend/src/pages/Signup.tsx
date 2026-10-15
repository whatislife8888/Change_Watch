/**
 * Signup.tsx — create an account. If the user arrived from the landing page with a URL
 * (?url=...), they go straight to Add page with that URL filled in.
 */
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useSignup } from '../api/hooks';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { AuthLayout } from './AuthLayout';
import s from './Auth.module.css';

export default function Signup() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const signup = useSignup();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [tooShort, setTooShort] = useState(false);
  const carriedUrl = params.get('url');
  const next = params.get('next');

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (password.length < 8) {
      setTooShort(true);
      return;
    }
    signup.mutate({ email, password, display_name: name }, {
      onSuccess: () => {
        if (carriedUrl) navigate(`/pages/new?url=${encodeURIComponent(carriedUrl)}`, { replace: true });
        else navigate(next && next.startsWith('/') ? next : '/', { replace: true });
      },
    });
  }

  return (
    <AuthLayout seedHint={carriedUrl}>
      <div>
        <h1 className={s.title}>Create your account</h1>
        <p className={s.lede} style={{ marginTop: 12 }}>
          {carriedUrl ? 'One step left. After this we start watching your page.' : 'Watch pages you care about. We ignore the noise and tell you when something real changes.'}
        </p>
      </div>
      <form className={s.form} onSubmit={onSubmit} noValidate>
        {signup.error && <div className={s.formError} role="alert">{signup.error.message}</div>}
        <Input label="Your name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} hint="Used in greetings and alerts." />
        <Input label="Email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} hint="Change alerts are sent here." />
        <Input
          label="Password"
          type="password"
          autoComplete="new-password"
          required
          value={password}
          onChange={(e) => { setPassword(e.target.value); setTooShort(false); }}
          hint="At least 8 characters."
          error={tooShort ? 'Use at least 8 characters.' : undefined}
        />
        <div className={s.actions}>
          <Button type="submit" variant="primary" loading={signup.isPending}>Create account</Button>
          <span className={s.switch}>Already have an account? <Link to="/login">Log in</Link></span>
        </div>
      </form>
    </AuthLayout>
  );
}
