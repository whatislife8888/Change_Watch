/** Dashboard.tsx — placeholder until Phase 2 (watches API). */
import { useMe } from '../api/hooks';
import { PageShell } from '../components/layout/PageShell';
import { greeting } from '../lib/time';

export default function Dashboard() {
  const { data: user } = useMe();
  return (
    <PageShell>
      <h1>{greeting()}, {user?.display_name}</h1>
    </PageShell>
  );
}
