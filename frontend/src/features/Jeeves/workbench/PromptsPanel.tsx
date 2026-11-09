import React, { useMemo, useState } from 'react';
import { Text, View } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import type { SavedPrompt } from './types';
import { LIMITS } from './types';
import { normalizeTags } from './validation';
import { BUILTIN_PROMPTS, inferVariables, projectPromptValues, renderPrompt } from './prompts';
import { Action, Badge, Editor, Empty, Field, Section, Toggle, confirmAction, styles } from './ui';
import type { PanelProps } from './ui';

function PromptEditor({ store, project, prompt, close }: PanelProps & { prompt?: SavedPrompt; close: () => void }) {
  const [title, setTitle] = useState(prompt?.title || '');
  const [description, setDescription] = useState(prompt?.description || '');
  const [template, setTemplate] = useState(prompt?.template || 'Help me with {{task}} in {{engine}}.');
  const [tags, setTags] = useState(prompt?.tags.join(', ') || '');
  const [global, setGlobal] = useState(prompt ? prompt.projectId === null : false);
  const [favorite, setFavorite] = useState(prompt?.favorite || false);
  const [variables, setVariables] = useState(inferVariables(template, prompt?.variables));
  const [error, setError] = useState('');
  const updateTemplate = (value: string) => {
    setTemplate(value);
    setVariables(inferVariables(value, variables));
  };
  const save = () => {
    try {
      const input = {
        title,
        description,
        template,
        variables,
        projectId: global ? null : project.id,
        tags: normalizeTags(tags),
        favorite,
      };
      const result = prompt
        ? store.dispatch({ type: 'prompt.update', id: prompt.id, revision: prompt.revision, patch: input })
        : store.dispatch({ type: 'prompt.create', input });
      if (result) close();
      else setError(store.getSnapshot().notice || 'Could not save the prompt.');
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Check the prompt fields.');
    }
  };
  return (
    <Editor visible title={prompt ? 'Edit prompt' : 'New reusable prompt'} close={close} footer={<Action label="Save prompt" icon="checkmark-outline" onPress={save} />}>
      <Field label="Prompt title" value={title} onChange={setTitle} maxLength={LIMITS.title} />
      <Field label="What this prompt is for" value={description} onChange={setDescription} multiline maxLength={LIMITS.summary} />
      <Field label="Prompt template" value={template} onChange={updateTemplate} multiline maxLength={LIMITS.context} hint="Use placeholders like {{task}} or {{engine}}. Variable names use lowercase letters, numbers and underscores." />
      <Field label="Prompt tags" value={tags} onChange={setTags} maxLength={500} />
      <Toggle label="Available in every project" value={global} onChange={setGlobal} />
      <Toggle label="Favorite prompt" value={favorite} onChange={setFavorite} />
      {variables.map(variable => <Section key={variable.key} title={`Variable: ${variable.key}`}>
        <Field label={`Label for ${variable.key}`} value={variable.label} onChange={label => setVariables(variables.map(item => item.key === variable.key ? { ...item, label } : item))} maxLength={100} />
        <Field label={`Help text for ${variable.key}`} value={variable.description} onChange={description => setVariables(variables.map(item => item.key === variable.key ? { ...item, description } : item))} maxLength={500} />
        <Field label={`Default for ${variable.key}`} value={variable.defaultValue} onChange={defaultValue => setVariables(variables.map(item => item.key === variable.key ? { ...item, defaultValue } : item))} maxLength={2000} />
        <Toggle label={`Require ${variable.key}`} value={variable.required} onChange={required => setVariables(variables.map(item => item.key === variable.key ? { ...item, required } : item))} />
      </Section>)}
      {error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
    </Editor>
  );
}

function PromptRunner({ prompt, project, store, use, close }: PanelProps & {
  prompt: SavedPrompt;
  use: (draft: string) => void;
  close: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(() => {
    const projectValues = projectPromptValues(project);
    return Object.fromEntries(prompt.variables.map(variable => [variable.key, projectValues[variable.key] || variable.defaultValue]));
  });
  const result = useMemo(() => {
    try { return { rendered: renderPrompt(prompt, values), error: '' }; }
    catch (error) { return { rendered: null, error: error instanceof Error ? error.message : 'Could not render the prompt.' }; }
  }, [prompt, values]);
  const ready = result.rendered && result.rendered.missing.length === 0;
  return (
    <Editor visible title={prompt.title} close={close}>
      <Text style={styles.muted}>{prompt.description}</Text>
      {prompt.variables.map(variable => <Field
        key={variable.key}
        label={variable.label + (variable.required ? ' *' : '')}
        value={values[variable.key] || ''}
        onChange={value => setValues({ ...values, [variable.key]: value })}
        hint={variable.description || undefined}
        maxLength={2000}
        multiline
      />)}
      <Section title="Prompt preview">
        {result.error && <Text style={styles.error}>{result.error}</Text>}
        {result.rendered && <Text selectable style={styles.text}>{result.rendered.text}</Text>}
        {!!result.rendered?.missing.length && <Text style={styles.error}>Complete: {result.rendered.missing.join(', ')}</Text>}
      </Section>
      <View style={styles.wrap}>
        <Action label="Use in Jeeves chat" icon="sparkles-outline" disabled={!ready} onPress={() => {
          if (!ready || !result.rendered) return;
          store.dispatch({ type: 'prompt.used', id: prompt.id });
          use(result.rendered.text);
          close();
        }} />
        <Action label="Copy completed prompt" icon="copy-outline" disabled={!ready} onPress={() => {
          if (!result.rendered) return;
          void Clipboard.setStringAsync(result.rendered.text).then(() => store.notify('Completed prompt copied.')).catch(() => store.notify('Clipboard is unavailable.'));
        }} />
      </View>
    </Editor>
  );
}

export default function PromptsPanel(props: PanelProps & { usePrompt: (draft: string) => void }) {
  const { state, project, store } = props;
  const [query, setQuery] = useState('');
  const [favorites, setFavorites] = useState(false);
  const [editor, setEditor] = useState<SavedPrompt | 'new' | null>(null);
  const [runner, setRunner] = useState<SavedPrompt | null>(null);
  const [templates, setTemplates] = useState(false);
  const readOnly = project.status === 'archived';
  const needle = query.trim().toLocaleLowerCase();
  const prompts = state.prompts.filter(prompt => (prompt.projectId === null || prompt.projectId === project.id)
    && (!favorites || prompt.favorite)
    && (!needle || [prompt.title, prompt.description, prompt.template, ...prompt.tags].some(value => value.toLocaleLowerCase().includes(needle))))
    .sort((a, b) => Number(b.favorite) - Number(a.favorite) || b.updatedAt - a.updatedAt);
  return (
    <View style={styles.stack}>
      <Section title="Reusable prompts" subtitle="Save useful ways to ask, fill in the details, and send the completed prompt to chat." action={<Action label="New prompt" icon="add" onPress={() => setEditor('new')} disabled={readOnly} />}>
        <Field label="Search prompts" value={query} onChange={setQuery} maxLength={200} />
        <Toggle label="Favorites only" value={favorites} onChange={setFavorites} />
        <Action label="Browse starter templates" icon="library-outline" selected={templates} onPress={() => setTemplates(!templates)} />
      </Section>
      {templates && <Section title="Starter templates" subtitle="Add any template as an editable prompt. Nothing is sent until you use it.">
        {BUILTIN_PROMPTS.map(template => <View key={template.title} style={styles.card}>
          <Text style={styles.label}>{template.title}</Text>
          <Text style={styles.muted}>{template.description}</Text>
          <Action label={`Add ${template.title}`} icon="add" disabled={readOnly} onPress={() => {
            const result = store.dispatch({ type: 'prompt.create', input: { ...template, projectId: project.id } });
            if (result) store.notify(`Added ${template.title}.`);
          }} />
        </View>)}
      </Section>}
      {!prompts.length && <Empty icon="chatbox-ellipses-outline" title="No matching prompts" message="Create a prompt with reusable variables or add a starter template." />}
      {prompts.map(prompt => <Section key={prompt.id} title={prompt.title} subtitle={prompt.description}>
        <View style={styles.wrap}>
          <Badge text={prompt.projectId === null ? 'All projects' : 'This project'} tone="accent" />
          <Badge text={`${prompt.useCount} uses`} />
          {prompt.favorite && <Badge text="Favorite" tone="amber" />}
          {prompt.tags.map(tag => <Badge key={tag} text={`#${tag}`} />)}
        </View>
        <Text numberOfLines={5} style={styles.muted}>{prompt.template}</Text>
        <Text style={styles.small}>{prompt.variables.length} variable(s)</Text>
        <View style={styles.wrap}>
          <Action label="Fill and use prompt" icon="play-outline" onPress={() => setRunner(prompt)} />
          <Action label="Edit prompt" icon="create-outline" onPress={() => setEditor(prompt)} disabled={readOnly} />
          <Action label={prompt.favorite ? 'Unfavorite prompt' : 'Favorite prompt'} icon={prompt.favorite ? 'star' : 'star-outline'} onPress={() => store.dispatch({ type: 'prompt.update', id: prompt.id, revision: prompt.revision, patch: { favorite: !prompt.favorite } })} disabled={readOnly} />
          <Action label="Delete prompt" icon="trash-outline" danger onPress={() => confirmAction('Delete prompt?', 'The saved template will be removed. Existing chat messages are unaffected.', () => store.dispatch({ type: 'prompt.delete', id: prompt.id, revision: prompt.revision }))} disabled={readOnly} />
        </View>
      </Section>)}
      {editor && <PromptEditor {...props} prompt={editor === 'new' ? undefined : editor} close={() => setEditor(null)} />}
      {runner && <PromptRunner {...props} prompt={runner} use={props.usePrompt} close={() => setRunner(null)} />}
    </View>
  );
}
