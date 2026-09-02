import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { StatusBadge } from './StatusBadge';

describe('StatusBadge', () => {
  it('always exposes a textual status in addition to color', () => {
    render(<StatusBadge status="broken_uuid" />);
    expect(screen.getByText('UUID не найден')).toBeVisible();
  });

  it('accepts an explicit accessible label', () => {
    render(<StatusBadge status="fixture" label="Capella · fixture" />);
    expect(screen.getByText('Capella · fixture')).toBeVisible();
  });
});
