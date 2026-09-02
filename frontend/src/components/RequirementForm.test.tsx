import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { Requirement } from '../lib/types';
import { RequirementForm, requirementFromForm, requirementToForm } from './RequirementForm';

const requirement: Requirement = {
  uid: 'SYS-002',
  mid: 'mid-2',
  document: '02_system.sdoc',
  nodeType: 'REQUIREMENT',
  type: 'System',
  status: 'Approved',
  priority: 'High',
  verificationMethod: 'Test',
  owner: 'Иван',
  source: '',
  tags: ['pressure'],
  title: 'Pressure',
  statement: 'The system shall monitor pressure.',
  rationale: 'Old rationale',
  acceptanceCriteria: 'Alarm in 100 ms.',
  comment: '',
  relations: [{ type: 'Parent', value: 'STK-001', role: 'Refines' }],
  revision: 'rev-1',
  sectionPath: [],
  architectureLinkCount: 0,
};

describe('RequirementForm', () => {
  it('maps values without changing canonical identifiers or relations', () => {
    const values = requirementToForm(requirement);
    const payload = requirementFromForm(
      { ...values, rationale: 'Новая\nпричина', tagsText: 'pressure, critical' },
      requirement,
    );
    expect(payload).toMatchObject({
      uid: 'SYS-002',
      revision: 'rev-1',
      rationale: 'Новая\nпричина',
      tags: ['pressure', 'critical'],
    });
    expect(payload.relations).toEqual(requirement.relations);
  });

  it('renders revision, submits edited rationale and exposes preview', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(
      <RequirementForm
        requirement={requirement}
        isSaving={false}
        isValidating={false}
        onSubmit={onSubmit}
        onValidate={vi.fn()}
      />,
    );
    expect(screen.getByTestId('requirement-revision')).toHaveTextContent('rev rev-1');
    const rationale = screen.getByTestId('requirement-rationale');
    await user.clear(rationale);
    await user.type(rationale, 'Updated rationale');
    await user.click(screen.getByRole('button', { name: 'Сохранить' }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        uid: 'SYS-002',
        rationale: 'Updated rationale',
        revision: 'rev-1',
      }),
    );
    await user.click(screen.getByRole('tab', { name: 'Preview' }));
    expect(screen.getByText('Updated rationale')).toBeVisible();
  });

  it('shows field validation and never submits an invalid new requirement', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(
      <RequirementForm
        isSaving={false}
        isValidating={false}
        onSubmit={onSubmit}
        onValidate={vi.fn()}
      />,
    );
    await user.click(screen.getByRole('button', { name: 'Сохранить' }));
    expect(await screen.findByText('Укажите UID')).toBeVisible();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
