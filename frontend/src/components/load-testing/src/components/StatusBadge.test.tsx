import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { StatusBadge, VerdictBadge } from './StatusBadge';

describe('StatusBadge', () => {
  it.each([
    ['running', 'Running'],
    ['completed', 'Completed'],
    ['failed', 'Failed'],
  ] as const)('renders %s', (status, label) => {
    render(<StatusBadge status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});

describe('VerdictBadge', () => {
  it('distinguishes pass, fail, and not applicable', () => {
    const { rerender } = render(<VerdictBadge pass />);
    expect(screen.getByText('Pass')).toBeInTheDocument();
    rerender(<VerdictBadge pass={false} />);
    expect(screen.getByText('Fail')).toBeInTheDocument();
    rerender(<VerdictBadge pass={null} na="info" />);
    expect(screen.getByText('info')).toBeInTheDocument();
  });
});
