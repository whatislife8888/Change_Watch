/** NotFound.tsx — shown for any unknown route. */
import { PageShell } from '../components/layout/PageShell';
import { ButtonLink } from '../components/ui/Button';
import { EmptyState } from '../components/ui/misc';

export default function NotFound() {
  return (
    <PageShell>
      <EmptyState title="This page doesn't exist" body="The link may be old, or the page was removed.">
        <ButtonLink to="/" variant="secondary">Back to your pages</ButtonLink>
      </EmptyState>
    </PageShell>
  );
}
