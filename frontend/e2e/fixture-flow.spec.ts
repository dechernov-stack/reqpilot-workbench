import { expect, test, type APIRequestContext } from '@playwright/test';
import { normalizeRequirement, normalizeTraceLinks } from '../src/lib/normalize';
import { requirementToUpdatePayload } from '../src/lib/api';
import type { Requirement, TraceLink } from '../src/lib/types';

const requirementUid = 'SYS-002';
const targetName = 'Evaluate Pressure Threshold';

async function readRequirement(request: APIRequestContext): Promise<Requirement> {
  const response = await request.get(`/api/requirements/${requirementUid}`);
  expect(response.ok()).toBeTruthy();
  return normalizeRequirement((await response.json()) as unknown);
}

async function readLinks(request: APIRequestContext): Promise<TraceLink[]> {
  const response = await request.get('/api/trace-links');
  expect(response.ok()).toBeTruthy();
  return normalizeTraceLinks((await response.json()) as unknown);
}

async function removeScenarioLinks(request: APIRequestContext): Promise<void> {
  const links = await readLinks(request);
  const matches = links.filter(
    (link) =>
      link.requirementUid === requirementUid &&
      link.targetNameSnapshot === targetName &&
      link.relation === 'satisfied_by',
  );
  for (const link of matches) {
    const suffix = link.revision ? `?revision=${encodeURIComponent(link.revision)}` : '';
    const response = await request.delete(
      `/api/trace-links/${encodeURIComponent(link.id)}${suffix}`,
    );
    expect(response.ok()).toBeTruthy();
  }
}

async function restoreRationale(request: APIRequestContext, original: Requirement): Promise<void> {
  const current = await readRequirement(request);
  if (current.rationale === original.rationale) return;
  const payload = requirementToUpdatePayload({ ...original, revision: current.revision });
  const response = await request.put(`/api/requirements/${requirementUid}`, {
    headers: { 'If-Match': current.revision },
    data: payload,
  });
  expect(response.ok()).toBeTruthy();
}

test('fixture: edit → link → graph → matrix → combined HTML', async ({ page, request }) => {
  const original = await readRequirement(request);
  await removeScenarioLinks(request);
  try {
    await page.goto('/');
    await expect(page.getByTestId('fixture-banner')).toContainText('Демо-архитектура');

    await page.getByRole('link', { name: 'Требования' }).click();
    await page.getByTestId(`requirement-row-${requirementUid}`).click();
    const revisionBefore = await page.getByTestId('requirement-revision').textContent();
    const rationale = page.getByTestId('requirement-rationale');
    await rationale.fill(`${original.rationale}\nPlaywright fixture check`);
    await page.getByRole('button', { name: 'Сохранить' }).click();
    await expect(page.getByTestId('requirement-revision')).not.toHaveText(revisionBefore ?? '');

    await page.getByRole('button', { name: 'Связать' }).click();
    const dialog = page.getByRole('dialog', { name: 'Связать с архитектурой' });
    await dialog.getByPlaceholder('Название, тип или UUID').fill(targetName);
    await dialog.getByRole('option').filter({ hasText: targetName }).click();
    await dialog.getByTestId('create-trace-link').click();
    await expect(dialog).toBeHidden();

    await page.getByRole('link', { name: 'Трассировка' }).click();
    await expect(page.getByTestId('traceability-graph')).toContainText(targetName);
    await expect(page.getByTestId('traceability-graph')).toContainText('satisfied_by');

    await page.getByRole('link', { name: 'Матрицы' }).click();
    await page.getByTestId('matrix-tab-requirements-functions').click();
    await expect(
      page.locator(`[data-testid^="matrix-cell-${requirementUid}-"][aria-label*="satisfied_by"]`),
    ).toBeVisible();

    await page.getByRole('link', { name: 'Экспорт' }).click();
    await page.getByTestId('export-combined-html').click();
    const jobs = page.getByTestId('export-jobs');
    await expect(jobs).toContainText('COMBINED-HTML', { ignoreCase: true });
    const download = jobs.getByRole('link', { name: /\.html/i }).first();
    await expect(download).toBeVisible();
  } finally {
    await removeScenarioLinks(request);
    await restoreRationale(request, original);
  }
});
