/**
 * Login.tsx — the log-in screen. On success it goes to `?next=` (where the user was heading) or home.
 */
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useLogin } from '../api/hooks';
import { AuthLayout } from './AuthLayout';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import s from './Auth.module.css';

export default function Login() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const login = useLogin();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const next = params.get('next');

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    login.mutate({ email, password }, {
      onSuccess: () => navigate(next && next.startsWith('/') ? next : '/', { replace: true }),
    });
  }

  return (
    <AuthLayout>
      <div>
        <h1 className={s.title}>Welcome back</h1>
        <p className={s.lede} style={{ marginTop: 12 }}>Log in to see what changed on the pages you watch.</p>
      </div>
      <form className={s.form} onSubmit={onSubmit} noValidate>
        {login.error && <div className={s.formError} role="alert">{login.error.message}</div>}
        <Input label="Email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <Input label="Password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        <div className={s.actions}>
          <Button type="submit" variant="primary" loading={login.isPending}>Log in</Button>
          <span className={s.switch}>
            New to ChangeWatch? <Link to={`/signup${next ? `?next=${encodeURIComponent(next)}` : ''}`}>Create an account</Link>
          </span>
        </div>
      </form>
    </AuthLayout>
  );
}
