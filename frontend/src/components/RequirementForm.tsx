import { zodResolver } from '@hookform/resolvers/zod';
import * as Tabs from '@radix-ui/react-tabs';
import { Eye, FilePenLine, Save, ShieldCheck } from 'lucide-react';
import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import type { Requirement, RequirementInput } from '../lib/types';

export const requirementFormSchema = z.object({
  uid: z
    .string()
    .trim()
    .min(2, 'Укажите UID')
    .regex(/^[A-Za-z0-9][A-Za-z0-9_.-]*$/, 'UID содержит недопустимые символы'),
  document: z.string().trim().min(1, 'Выберите документ'),
  type: z.string().trim().min(1, 'Укажите тип'),
  status: z.string().trim().min(1, 'Укажите статус'),
  priority: z.string().trim().min(1, 'Укажите приоритет'),
  verificationMethod: z.string().trim().min(1, 'Укажите метод проверки'),
  owner: z.string().trim().min(1, 'Укажите владельца'),
  source: z.string(),
  tagsText: z.string(),
  title: z.string().trim().min(3, 'Название слишком короткое'),
  statement: z.string().trim().min(3, 'Формулировка обязательна'),
  rationale: z.string(),
  acceptanceCriteria: z.string().trim().min(3, 'Критерии приёмки обязательны'),
  comment: z.string(),
});

export type RequirementFormValues = z.infer<typeof requirementFormSchema>;

const newRequirementDefaults: RequirementFormValues = {
  uid: '',
  document: '02_system.sdoc',
  type: 'System',
  status: 'Draft',
  priority: 'Medium',
  verificationMethod: 'Test',
  owner: '',
  source: '',
  tagsText: '',
  title: '',
  statement: '',
  rationale: '',
  acceptanceCriteria: '',
  comment: '',
};

export function requirementToForm(requirement?: Requirement): RequirementFormValues {
  if (!requirement) return newRequirementDefaults;
  return {
    uid: requirement.uid,
    document: requirement.document,
    type: requirement.type,
    status: requirement.status,
    priority: requirement.priority,
    verificationMethod: requirement.verificationMethod,
    owner: requirement.owner,
    source: requirement.source,
    tagsText: requirement.tags.join(', '),
    title: requirement.title,
    statement: requirement.statement,
    rationale: requirement.rationale,
    acceptanceCriteria: requirement.acceptanceCriteria,
    comment: requirement.comment,
  };
}

export function requirementFromForm(
  values: RequirementFormValues,
  requirement?: Requirement,
): RequirementInput {
  return {
    uid: values.uid.trim(),
    document: values.document.trim(),
    nodeType: requirement?.nodeType ?? 'REQUIREMENT',
    type: values.type.trim(),
    status: values.status.trim(),
    priority: values.priority.trim(),
    verificationMethod: values.verificationMethod.trim(),
    owner: values.owner.trim(),
    source: values.source.trim(),
    tags: values.tagsText
      .split(',')
      .map((tag) => tag.trim())
      .filter(Boolean),
    title: values.title.trim(),
    statement: values.statement.trim(),
    rationale: values.rationale,
    acceptanceCriteria: values.acceptanceCriteria.trim(),
    comment: values.comment,
    relations: requirement?.relations ?? [],
    ...(requirement?.revision ? { revision: requirement.revision } : {}),
  };
}

interface RequirementFormProps {
  requirement?: Requirement;
  isSaving: boolean;
  isValidating: boolean;
  saveError?: string | undefined;
  onSubmit: (input: RequirementInput) => void;
  onValidate: () => void;
  onCancel?: () => void;
}

export function RequirementForm({
  requirement,
  isSaving,
  isValidating,
  saveError,
  onSubmit,
  onValidate,
  onCancel,
}: RequirementFormProps) {
  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors, isDirty },
  } = useForm<RequirementFormValues>({
    resolver: zodResolver(requirementFormSchema),
    defaultValues: requirementToForm(requirement),
  });
  useEffect(() => reset(requirementToForm(requirement)), [requirement, reset]);
  const values = watch();

  return (
    <Tabs.Root defaultValue="editor" className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between border-b border-line px-4">
        <Tabs.List className="flex" aria-label="Режим редактирования">
          <Tabs.Trigger className="tab-trigger" value="editor">
            <FilePenLine aria-hidden="true" className="h-4 w-4" />
            Редактор
          </Tabs.Trigger>
          <Tabs.Trigger className="tab-trigger" value="preview">
            <Eye aria-hidden="true" className="h-4 w-4" />
            Preview
          </Tabs.Trigger>
        </Tabs.List>
        {requirement ? (
          <span className="font-mono text-[11px] text-steel" data-testid="requirement-revision">
            rev {requirement.revision || '—'}
          </span>
        ) : null}
      </div>
      <Tabs.Content
        value="editor"
        className="min-h-0 flex-1 overflow-y-auto p-4 focus:outline-none"
      >
        <form
          id="requirement-form"
          className="space-y-4"
          onSubmit={(event) =>
            void handleSubmit((data) => onSubmit(requirementFromForm(data, requirement)))(event)
          }
        >
          <div className="grid grid-cols-2 gap-3">
            <Field label="UID" error={errors.uid?.message}>
              <input
                className="input w-full font-mono"
                data-testid="requirement-uid"
                readOnly={Boolean(requirement)}
                {...register('uid')}
              />
            </Field>
            <Field label="Документ" error={errors.document?.message}>
              <select
                className="select w-full"
                disabled={Boolean(requirement)}
                {...register('document')}
              >
                <option value="01_stakeholder.sdoc">Stakeholder</option>
                <option value="02_system.sdoc">System</option>
                <option value="03_software_interface.sdoc">Software / Interface</option>
                <option value="04_safety.sdoc">Safety</option>
                <option value="05_tests.sdoc">Tests</option>
              </select>
            </Field>
          </div>
          <Field label="Название" error={errors.title?.message}>
            <input
              className="input w-full"
              data-testid="requirement-title"
              {...register('title')}
            />
          </Field>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Тип" error={errors.type?.message}>
              <select className="select w-full" {...register('type')}>
                {['Stakeholder', 'System', 'Software', 'Interface', 'Safety', 'TestCase'].map(
                  (type) => (
                    <option key={type}>{type}</option>
                  ),
                )}
              </select>
            </Field>
            <Field label="Статус" error={errors.status?.message}>
              <select className="select w-full" {...register('status')}>
                {['Draft', 'Review', 'Approved', 'Deprecated'].map((status) => (
                  <option key={status}>{status}</option>
                ))}
              </select>
            </Field>
            <Field label="Приоритет" error={errors.priority?.message}>
              <select className="select w-full" {...register('priority')}>
                {['Critical', 'High', 'Medium', 'Low'].map((priority) => (
                  <option key={priority}>{priority}</option>
                ))}
              </select>
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Владелец" error={errors.owner?.message}>
              <input className="input w-full" {...register('owner')} />
            </Field>
            <Field label="Метод проверки" error={errors.verificationMethod?.message}>
              <select className="select w-full" {...register('verificationMethod')}>
                {['Test', 'Analysis', 'Inspection', 'Demonstration', 'NotApplicable'].map(
                  (method) => (
                    <option key={method}>{method}</option>
                  ),
                )}
              </select>
            </Field>
          </div>
          <Field label="Формулировка" error={errors.statement?.message}>
            <textarea
              className="textarea w-full"
              data-testid="requirement-statement"
              {...register('statement')}
            />
          </Field>
          <Field label="Обоснование" error={errors.rationale?.message}>
            <textarea
              className="textarea w-full"
              data-testid="requirement-rationale"
              {...register('rationale')}
            />
          </Field>
          <Field label="Критерии приёмки" error={errors.acceptanceCriteria?.message}>
            <textarea className="textarea w-full" {...register('acceptanceCriteria')} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Источник" error={errors.source?.message}>
              <input className="input w-full" {...register('source')} />
            </Field>
            <Field label="Теги через запятую" error={errors.tagsText?.message}>
              <input className="input w-full" {...register('tagsText')} />
            </Field>
          </div>
          <Field label="Комментарий" error={errors.comment?.message}>
            <textarea className="textarea min-h-16 w-full" {...register('comment')} />
          </Field>
          {saveError ? (
            <p
              className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800"
              role="alert"
            >
              {saveError}
            </p>
          ) : null}
        </form>
      </Tabs.Content>
      <Tabs.Content
        value="preview"
        className="min-h-0 flex-1 overflow-y-auto p-5 focus:outline-none"
      >
        <article className="prose-preview">
          <div className="flex items-center gap-2 text-xs text-steel">
            <span className="mono-id">{values.uid || 'NEW-UID'}</span>
            <span>·</span>
            <span>{values.type}</span>
            <span>·</span>
            <span>{values.status}</span>
          </div>
          <h2>{values.title || 'Название требования'}</h2>
          <PreviewSection title="Формулировка" value={values.statement} />
          <PreviewSection title="Обоснование" value={values.rationale} />
          <PreviewSection title="Критерии приёмки" value={values.acceptanceCriteria} />
        </article>
      </Tabs.Content>
      <div className="flex items-center justify-between gap-3 border-t border-line bg-slate-50 px-4 py-3">
        <button
          className="button-secondary"
          type="button"
          disabled={isValidating}
          onClick={onValidate}
        >
          <ShieldCheck aria-hidden="true" className="h-4 w-4" />
          {isValidating ? 'Проверка…' : 'Validate'}
        </button>
        <div className="flex items-center gap-2">
          {onCancel ? (
            <button className="button-secondary" type="button" onClick={onCancel}>
              Отмена
            </button>
          ) : null}
          <button
            className="button-primary"
            form="requirement-form"
            type="submit"
            disabled={isSaving || (!isDirty && Boolean(requirement))}
          >
            <Save aria-hidden="true" className="h-4 w-4" />
            {isSaving ? 'Сохранение…' : 'Сохранить'}
          </button>
        </div>
      </div>
    </Tabs.Root>
  );
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string | undefined;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="field-label">{label}</span>
      {children}
      {error ? <span className="field-error">{error}</span> : null}
    </label>
  );
}

function PreviewSection({ title, value }: { title: string; value: string }) {
  return (
    <section>
      <h3>{title}</h3>
      <p className="whitespace-pre-wrap">{value || '—'}</p>
    </section>
  );
}
