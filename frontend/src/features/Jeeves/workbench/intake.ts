import type { CardInput, NoteInput, TaskInput } from './domain';
import type { Priority, TaskStatus } from './types';
import { LIMITS, PRIORITIES, TASK_STATUSES } from './types';
import { assertText, normalizeTags, validDate, WorkbenchError } from './validation';

export interface IntakeRow<T> {
  line: number;
  value: T | null;
  errors: string[];
  warnings: string[];
}

export interface IntakePreview<T> {
  rows: IntakeRow<T>[];
  valid: number;
  invalid: number;
  warnings: string[];
}

export interface DelimitedTable {
  rows: string[][];
  rowLines: number[];
  delimiter: ',' | '\t';
}

/** Parse RFC-style quoting, including escaped quotes and multiline cells, with bounded input. */
export function parseDelimited(input: string, delimiter: ',' | '\t' = ','): DelimitedTable {
  if (input.length > 500000) throw new WorkbenchError('Paste at most 500,000 characters at a time.');
  const text = input.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n');
  const rows: string[][] = [];
  const rowLines: number[] = [];
  let row: string[] = [];
  let cell = '';
  let quoted = false;
  let closedQuote = false;
  let line = 1;
  let rowLine = 1;
  const finishCell = () => {
    row.push(cell);
    cell = '';
    closedQuote = false;
    if (row.length > 30) throw new WorkbenchError(`Line ${rowLine}: too many columns.`);
  };
  const finishRow = () => {
    finishCell();
    if (row.some(value => value.trim())) {
      rows.push(row);
      rowLines.push(rowLine);
    }
    row = [];
    if (rows.length > 501) throw new WorkbenchError('Import at most 500 data rows at a time.');
  };
  for (let index = 0; index < text.length; index++) {
    const character = text[index];
    if (quoted) {
      if (character === '"') {
        if (text[index + 1] === '"') {
          cell += '"';
          index++;
        } else {
          quoted = false;
          closedQuote = true;
        }
      } else {
        cell += character;
        if (character === '\n') line++;
      }
      if (cell.length > LIMITS.body) throw new WorkbenchError(`Line ${rowLine}: a cell is too long.`);
      continue;
    }
    if (character === delimiter) {
      finishCell();
    } else if (character === '\n') {
      finishRow();
      line++;
      rowLine = line;
    } else if (character === '"' && cell.length === 0 && !closedQuote) {
      quoted = true;
    } else if (closedQuote && character !== ' ' && character !== '\r') {
      throw new WorkbenchError(`Line ${line}: unexpected text after a closing quote.`);
    } else if (!closedQuote) {
      cell += character;
    }
    if (cell.length > LIMITS.body) throw new WorkbenchError(`Line ${rowLine}: a cell is too long.`);
  }
  if (quoted) throw new WorkbenchError(`Line ${rowLine}: an opening quote was not closed.`);
  if (cell.length || row.length || closedQuote) finishRow();
  return { rows, rowLines, delimiter };
}

function tableObjects(input: string, required: string[], delimiter: ',' | '\t') {
  const table = parseDelimited(input, delimiter);
  if (!table.rows.length) throw new WorkbenchError('Paste a header row and at least one data row.');
  const headers = table.rows[0].map(header => header.trim().toLocaleLowerCase().replace(/[ _-]+/g, '_'));
  if (new Set(headers).size !== headers.length) throw new WorkbenchError('Column names must be unique.');
  for (const key of required) {
    if (!headers.includes(key)) throw new WorkbenchError(`Missing required column: ${key}.`);
  }
  return table.rows.slice(1).map((row, index) => {
    const values: Record<string, string> = Object.create(null);
    headers.forEach((key, column) => { values[key] = row[column] || ''; });
    return {
      line: table.rowLines[index + 1],
      values,
      errors: row.length > headers.length ? ['This row contains more cells than the header.'] : [],
    };
  });
}

function finish<T>(rows: IntakeRow<T>[]): IntakePreview<T> {
  return {
    rows,
    valid: rows.filter(row => row.value !== null && !row.errors.length).length,
    invalid: rows.filter(row => row.value === null || row.errors.length > 0).length,
    warnings: rows.some(row => row.warnings.length) ? ['Some rows have warnings. Review them before importing.'] : [],
  };
}

export function previewTaskTable(input: string, projectId: string, delimiter: ',' | '\t' = ','): IntakePreview<TaskInput> {
  const seen = new Set<string>();
  const rows = tableObjects(input, ['title'], delimiter).map(({ line, values, errors }): IntakeRow<TaskInput> => {
    const warnings: string[] = [];
    try {
      const title = assertText(values.title.trim(), 'Title', LIMITS.title, true);
      const key = title.toLocaleLowerCase();
      if (seen.has(key)) warnings.push('Another imported row has the same title.');
      seen.add(key);
      const status = (values.status?.trim() || 'inbox') as TaskStatus;
      const priority = (values.priority?.trim() || 'normal') as Priority;
      if (!TASK_STATUSES.includes(status)) errors.push('Unknown task status.');
      if (!PRIORITIES.includes(priority)) errors.push('Unknown priority.');
      const rawEstimate = values.estimate_minutes || values.estimate || '25';
      const estimateMinutes = Number(rawEstimate);
      if (!Number.isInteger(estimateMinutes) || estimateMinutes < 0 || estimateMinutes > 10080) errors.push('Estimate must be a whole number from 0 through 10080.');
      const dueDate = values.due_date?.trim() || null;
      if (dueDate && !validDate(dueDate)) errors.push('Due date must use YYYY-MM-DD and be a real date.');
      const description = assertText(values.description || '', 'Description', LIMITS.body);
      const tags = normalizeTags((values.tags || '').split(/[;,]/));
      if (values.dependencies?.trim()) warnings.push('Dependencies are not imported by title. Link them after reviewing the tasks.');
      return {
        line,
        value: { projectId, title, description, status, priority, estimateMinutes, dueDate, tags },
        errors,
        warnings,
      };
    } catch (error) {
      return { line, value: null, errors: [...errors, error instanceof Error ? error.message : 'Invalid row.'], warnings };
    }
  });
  return finish(rows);
}

export function previewCardTable(input: string, projectId: string, delimiter: ',' | '\t' = '\t'): IntakePreview<CardInput> {
  const seen = new Set<string>();
  const rows = tableObjects(input, ['question', 'answer'], delimiter).map(({ line, values, errors }): IntakeRow<CardInput> => {
    const warnings: string[] = [];
    try {
      const question = assertText(values.question.trim(), 'Question', LIMITS.summary, true);
      const answer = assertText(values.answer.trim(), 'Answer', LIMITS.answer, true);
      const key = question.toLocaleLowerCase();
      if (seen.has(key)) warnings.push('Another row asks the same question.');
      seen.add(key);
      const hint = assertText(values.hint || '', 'Hint', LIMITS.summary);
      const explanation = assertText(values.explanation || '', 'Explanation', LIMITS.answer);
      const tags = normalizeTags((values.tags || '').split(/[;,]/));
      if (values.state || values.next_review) warnings.push('Scheduling fields are ignored. Imported cards start as new.');
      return { line, value: { projectId, question, answer, hint, explanation, tags }, errors, warnings };
    } catch (error) {
      return { line, value: null, errors: [...errors, error instanceof Error ? error.message : 'Invalid row.'], warnings };
    }
  });
  return finish(rows);
}

export function previewMarkdownTasks(input: string, projectId: string): IntakePreview<TaskInput> {
  assertText(input, 'Task list', 100000);
  const rows: IntakeRow<TaskInput>[] = [];
  const seen = new Set<string>();
  input.replace(/\r\n/g, '\n').split('\n').forEach((line, index) => {
    const match = /^\s*(?:[-*+]\s+|\d+[.)]\s+)(?:\[([ xX])\]\s*)?(.+)$/.exec(line);
    if (!match) return;
    const title = match[2].trim();
    const warnings: string[] = [];
    const errors: string[] = [];
    if (title.length > LIMITS.title) errors.push(`Task title exceeds ${LIMITS.title} characters.`);
    if (seen.has(title.toLocaleLowerCase())) warnings.push('Duplicate title in this list.');
    seen.add(title.toLocaleLowerCase());
    rows.push({
      line: index + 1,
      value: {
        projectId,
        title,
        status: match[1]?.toLocaleLowerCase() === 'x' ? 'done' : 'inbox',
        estimateMinutes: 0,
      },
      errors,
      warnings,
    });
  });
  if (!rows.length) throw new WorkbenchError('No bullet points or numbered tasks were found.');
  if (rows.length > 200) throw new WorkbenchError('Import at most 200 tasks from a pasted list.');
  return finish(rows);
}

export function previewMarkdownNotes(input: string, projectId: string): IntakePreview<NoteInput> {
  assertText(input, 'Notes', 200000);
  const lines = input.replace(/\r\n/g, '\n').split('\n');
  const sections: { title: string; body: string[]; line: number }[] = [];
  let current: typeof sections[number] | null = null;
  let fenced = false;
  lines.forEach((line, index) => {
    if (/^\s*```/.test(line)) fenced = !fenced;
    const match = !fenced ? /^#{1,2}\s+(.+)$/.exec(line) : null;
    if (match) {
      current = { title: match[1].trim(), body: [], line: index + 1 };
      sections.push(current);
    } else if (current) {
      current.body.push(line);
    } else if (line.trim()) {
      current = { title: 'Imported notes', body: [line], line: index + 1 };
      sections.push(current);
    }
  });
  if (!sections.length) throw new WorkbenchError('Paste at least one note.');
  if (sections.length > 100) throw new WorkbenchError('Import at most 100 notes at a time.');
  return finish(sections.map(section => {
    const body = section.body.join('\n').trim();
    const errors: string[] = [];
    if (section.title.length > LIMITS.title) errors.push('Note title is too long.');
    if (body.length > LIMITS.body) errors.push('Note body is too long.');
    return {
      line: section.line,
      value: { projectId, title: section.title, body, confidence: 'unverified' },
      errors,
      warnings: body ? [] : ['This section has no body.'],
    };
  }));
}

export function validIntakeValues<T>(preview: IntakePreview<T>): T[] {
  if (preview.invalid > 0) throw new WorkbenchError('Resolve invalid rows before importing. No partial import was applied.');
  return preview.rows.map(row => row.value).filter((value): value is T => value !== null);
}
