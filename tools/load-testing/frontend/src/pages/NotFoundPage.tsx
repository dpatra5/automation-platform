import { Compass } from 'lucide-react';

import { ButtonLink } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';

export function NotFoundPage() {
  return (
    <EmptyState
      icon={<Compass className="size-5" />}
      title="Page not found"
      description="The page you're looking for doesn't exist."
      action={
        <ButtonLink to="/" variant="primary">
          Go to dashboard
        </ButtonLink>
      }
    />
  );
}
