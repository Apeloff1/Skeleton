import React from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Banner, Button, Card, SectionTitle } from '../primitives';
import { C } from '../theme';

export interface ProjectListItem {
  id: string;
  title: string;
  status: string;
  updated: string;
}

export function DashboardScreen({
  phase, error, holdSaves, projects, accountLabel, guestNote, onCreate, onOpen, onRetry, onStartFresh, onAccount, onSettings, onSignIn,
}: {
  phase: 'loading' | 'ready' | 'error';
  error: string | null;
  holdSaves: boolean;
  projects: ProjectListItem[];
  accountLabel: string | null;
  guestNote: string | null;
  onCreate: () => void;
  onOpen: (id: string) => void;
  onRetry: () => void;
  onStartFresh: () => void;
  onAccount: () => void;
  onSettings: () => void;
  onSignIn: () => void;
}) {
  return (
    <ScrollView contentContainerStyle={st.body} testID="studio-dashboard" keyboardShouldPersistTaps="handled">
      <SectionTitle hint={accountLabel ? `Signed in as ${accountLabel}` : 'On this device'}>Your projects</SectionTitle>
      <View style={st.row}>
        <Button label="Account" tone="ghost" compact onPress={onAccount} testID="studio-account-link" />
        <Button label="Settings" tone="ghost" compact onPress={onSettings} testID="studio-settings-link" />
        {accountLabel ? null : <Button label="Sign in" tone="secondary" compact onPress={onSignIn} testID="studio-signin-link" />}
      </View>
      {guestNote ? <Banner tone="idle" testID="studio-guest-note">{guestNote}</Banner> : null}
      {phase === 'loading' ? (
        <View style={st.row} accessibilityLiveRegion="polite">
          <ActivityIndicator color={C.accent} accessibilityLabel="Loading projects" />
          <Text style={st.copy}>Loading projects…</Text>
        </View>
      ) : null}
      {phase === 'error' || holdSaves ? (
        <View>
          <Banner tone="bad" testID="studio-projects-error">{error || 'Saved projects could not be read on this device.'}</Banner>
          <Text style={st.copy}>Retry keeps the save as it is. Start fresh replaces the unreadable save on this device and lets you create a project.</Text>
          <View style={st.row}>
            <Button label="Retry" onPress={onRetry} busy={phase === 'loading'} testID="studio-retry-projects" />
            <Button label="Start fresh" tone="danger" onPress={onStartFresh} testID="studio-start-fresh" />
          </View>
        </View>
      ) : null}
      {phase === 'ready' && !holdSaves && projects.length === 0 ? (
        <Card testID="studio-empty">
          <Text style={st.copy}>No projects yet. Start with a brief — a sentence or two about the game.</Text>
        </Card>
      ) : null}
      {phase !== 'loading' && !holdSaves ? projects.map((project) => (
        <Card key={project.id} testID={`studio-project-${project.id}`}>
          <Text style={st.title}>{project.title}</Text>
          <Text style={st.meta}>{project.status} · updated {project.updated}</Text>
          <Button
            label={`Open ${project.title}`}
            tone="secondary"
            compact
            onPress={() => onOpen(project.id)}
            testID={`studio-open-${project.id}`}
            a11yHint={project.status}
          />
        </Card>
      )) : null}
      {holdSaves ? null : (
        <Button label="New project from a brief" onPress={onCreate} disabled={phase === 'loading'} testID="studio-create" a11yHint="Opens the forge questionnaire for a new project" />
      )}
    </ScrollView>
  );
}

const st = StyleSheet.create({
  body: { padding: 16, paddingBottom: 48, gap: 8 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center' },
  copy: { color: C.text, fontSize: 15, lineHeight: 22 },
  title: { color: C.textStrong, fontSize: 16, fontWeight: '800' },
  meta: { color: C.mute, fontSize: 13, marginTop: 4, marginBottom: 8 },
});
