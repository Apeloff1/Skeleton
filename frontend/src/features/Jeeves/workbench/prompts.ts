import type { PromptInput } from './domain';
import type { Project, PromptVariable, SavedPrompt } from './types';
import { assertText, WorkbenchError } from './validation';

export interface PromptRender {
  text: string;
  missing: string[];
  used: string[];
  unused: string[];
}

export function templateKeys(template: string): string[] {
  return [...new Set([...template.matchAll(/\{\{\s*([a-z][a-z0-9_]*)\s*\}\}/g)].map(match => match[1]))];
}

export function inferVariables(template: string, existing: PromptVariable[] = []): PromptVariable[] {
  return templateKeys(template).map(key => existing.find(variable => variable.key === key) || {
    key,
    label: key.replace(/_/g, ' ').replace(/^./, character => character.toUpperCase()),
    description: '',
    defaultValue: '',
    required: true,
  });
}

export function renderPrompt(prompt: Pick<SavedPrompt, 'template' | 'variables'>, values: Record<string, string>): PromptRender {
  const keys = templateKeys(prompt.template);
  const missing: string[] = [];
  const used: string[] = [];
  const definitions = new Map(prompt.variables.map(variable => [variable.key, variable]));
  const text = prompt.template.replace(/\{\{\s*([a-z][a-z0-9_]*)\s*\}\}/g, (placeholder, key: string) => {
    const definition = definitions.get(key);
    if (!definition) {
      if (!missing.includes(key)) missing.push(key);
      return placeholder;
    }
    const supplied = Object.prototype.hasOwnProperty.call(values, key) ? values[key] : definition.defaultValue;
    const value = assertText(supplied, definition.label, 2000);
    if (definition.required && !value.trim()) {
      if (!missing.includes(key)) missing.push(key);
      return placeholder;
    }
    if (!used.includes(key)) used.push(key);
    // Replacement output is not parsed again, so user values cannot create another interpolation pass.
    return value;
  });
  if (text.length > 16000) throw new WorkbenchError('The completed prompt exceeds the chat message limit. Shorten some fields.');
  return {
    text,
    missing,
    used,
    unused: Object.keys(values).filter(key => !keys.includes(key)),
  };
}

export function projectPromptValues(project: Project): Record<string, string> {
  return {
    project: project.title,
    goal: project.goal,
    engine: project.engine,
    experience: project.experience,
    context: project.context,
    budget: `${project.weeklyMinutes} minutes per week`,
  };
}

function builtIn(title: string, description: string, template: string, tags: string[]): PromptInput {
  return {
    title,
    description,
    template,
    tags,
    favorite: false,
    projectId: null,
    variables: inferVariables(template),
  };
}

/** Opt-in templates: installing them creates ordinary editable records, never hidden instructions. */
export const BUILTIN_PROMPTS: PromptInput[] = [
  builtIn(
    'Scope a playable prototype',
    'Turn a game idea into a small prototype with observable completion criteria.',
    [
      'Help me scope a playable prototype for {{project}}.',
      'Goal: {{goal}}',
      'Engine: {{engine}}',
      'Experience: {{experience}}',
      'Available time: {{budget}}',
      '',
      'Propose the smallest core loop, a short milestone sequence, and a concrete test for each milestone.',
      'State assumptions and ask about essential missing constraints. Separate necessary work from optional polish.',
      'Do not claim the plan has been implemented or tested.',
    ].join('\n'),
    ['planning', 'prototype'],
  ),
  builtIn(
    'Debug a reproducible failure',
    'Structure a debugging conversation around evidence and a minimal reproduction.',
    [
      'Help me investigate a bug in {{engine}}.',
      'Expected behavior: {{expected}}',
      'Actual behavior: {{actual}}',
      'Relevant code or error: {{evidence}}',
      '',
      'First separate observations from hypotheses. Suggest the cheapest discriminating check.',
      'Explain what each possible result would mean. Ask for a minimal reproduction if the evidence is insufficient.',
      'Keep proposed changes narrow and include a regression check.',
    ].join('\n'),
    ['debugging', 'evidence'],
  ),
  builtIn(
    'Review a gameplay mechanic',
    'Evaluate clarity, feedback, balance and the smallest useful playtest.',
    [
      'Review this gameplay mechanic: {{mechanic}}',
      'Player audience: {{audience}}',
      'Intended player experience: {{experience}}',
      '',
      'Consider player goals, inputs, feedback, failure states, accessibility and exploits.',
      'Give two plausible alternatives with tradeoffs, then design a small playtest that can distinguish them.',
      'Label guesses as guesses and avoid inventing player research.',
    ].join('\n'),
    ['design', 'playtest'],
  ),
  builtIn(
    'Explain code at my level',
    'Get a grounded explanation followed by a small practice exercise.',
    [
      'Explain the following code for someone at {{experience}} level.',
      'Language or engine: {{engine}}',
      'Code: {{code}}',
      '',
      'Describe the inputs, state changes, control flow and outputs.',
      'Explain one important edge case and show how to inspect it.',
      'End with a small modification I can make myself and a check for whether it works.',
    ].join('\n'),
    ['learning', 'code'],
  ),
  builtIn(
    'Design an experiment',
    'Turn a development uncertainty into a test with a measurable outcome.',
    [
      'I need to test this hypothesis: {{hypothesis}}',
      'Project constraints: {{context}}',
      '',
      'Define the independent variable, observations, comparison baseline and a stopping rule.',
      'Identify confounders and what evidence would falsify the hypothesis.',
      'Keep the experiment feasible within {{budget}}. Do not invent results.',
    ].join('\n'),
    ['experiment', 'evidence'],
  ),
  builtIn(
    'Compare implementation options',
    'Choose between approaches using explicit constraints instead of unsupported rankings.',
    [
      'Compare these implementation options: {{options}}',
      'Goal: {{goal}}',
      'Engine and environment: {{engine}}',
      'Constraints: {{context}}',
      '',
      'Compare complexity, performance risks, maintainability and reversibility.',
      'Name what would change your recommendation. Suggest a small spike to resolve the most important uncertainty.',
    ].join('\n'),
    ['architecture', 'decision'],
  ),
  builtIn(
    'Prepare a focused work session',
    'Break a task into steps that fit a bounded session.',
    [
      'Help me prepare a {{minutes}}-minute work session.',
      'Task: {{task}}',
      'Starting point: {{context}}',
      '',
      'Define one realistic outcome, the first action, a short checklist and a verification step.',
      'List likely blockers and what to save if the session ends before completion.',
    ].join('\n'),
    ['focus', 'planning'],
  ),
  builtIn(
    'Turn notes into study questions',
    'Draft answerable recall questions from material you provide.',
    [
      'Create study questions from these notes: {{notes}}',
      'Learner level: {{experience}}',
      '',
      'Make each question test one idea. Include the answer, a short explanation and a common misconception.',
      'Use only the supplied material for factual claims. Mark missing information instead of filling it in.',
      'Include application questions as well as definitions.',
    ].join('\n'),
    ['study', 'notes'],
  ),
  builtIn(
    'Review a finished milestone',
    'Reflect on evidence, remaining risks and the next decision.',
    [
      'Help me review this milestone: {{milestone}}',
      'What I built: {{changes}}',
      'Verification performed: {{evidence}}',
      'Remaining concerns: {{concerns}}',
      '',
      'Separate demonstrated behavior from unverified claims.',
      'Summarize lessons, identify the most useful follow-up, and suggest what to record in a decision note.',
    ].join('\n'),
    ['retrospective', 'verification'],
  ),
  builtIn(
    'Investigate performance',
    'Start from a measured workload and avoid speculative optimization.',
    [
      'Help me investigate a performance problem.',
      'Environment: {{engine}}',
      'Workload: {{workload}}',
      'Measurements: {{measurements}}',
      'Target: {{goal}}',
      '',
      'Suggest an instrumentation plan, likely bottleneck classes and a controlled comparison.',
      'Do not assert a root cause without evidence. Include how to detect a regression in correctness.',
    ].join('\n'),
    ['performance', 'debugging'],
  ),
  builtIn(
    'Improve accessibility',
    'Review a game interaction for concrete barriers and testable improvements.',
    [
      'Review this game interaction for accessibility: {{interaction}}',
      'Target platforms and controls: {{platforms}}',
      'Current constraints: {{context}}',
      '',
      'Consider input alternatives, visual and audio cues, readable text, motion, timing and difficulty settings.',
      'Prioritize a few practical improvements and explain how I can test each with users or assistive settings.',
      'Do not claim compliance based on this description alone.',
    ].join('\n'),
    ['accessibility', 'design'],
  ),
  builtIn(
    'Prepare a release checklist',
    'Create a scope-appropriate verification and rollback checklist.',
    [
      'Prepare a release checklist for {{project}}.',
      'Platform: {{platforms}}',
      'Changes in this release: {{changes}}',
      'Known risks: {{concerns}}',
      '',
      'Cover critical user flows, saved data, error handling, packaging and a rollback or recovery plan.',
      'Separate checks already evidenced from checks still required. Keep the checklist appropriate to a small team.',
    ].join('\n'),
    ['release', 'verification'],
  ),
];
