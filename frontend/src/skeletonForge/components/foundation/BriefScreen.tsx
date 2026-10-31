/**
 * Project brief. The questionnaire is the existing forge flow; this screen
 * only adds a way back to projects, the build, and the full cockpit.
 */
import React from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import type { QuestionnaireAction, QuestionnaireState } from '../../questionnaire';
import type { Beat, EraRow, GenerationRow, RunRequest } from '../../types';
import { Banner, Button, SectionTitle } from '../primitives';
import QuestionnaireFlow from '../QuestionnaireFlow';

export function BriefScreen({
  title, catalogLoading, catalogError, onRetryCatalog, onProjects, onViewBuild, onOpenCockpit,
  conflict, state, dispatch, beats, beatsLive, eras, generations, onForge, forging, composeSummary,
}: {
  title: string;
  catalogLoading: boolean;
  catalogError: string | null;
  onRetryCatalog: () => void;
  onProjects: () => void;
  onViewBuild: () => void;
  onOpenCockpit: () => void;
  conflict: { title: string; onConfirm: () => void; onKeep: () => void; onView: () => void } | null;
  state: QuestionnaireState;
  dispatch: (action: QuestionnaireAction) => void;
  beats: Beat[];
  beatsLive?: boolean;
  eras?: EraRow[];
  generations?: GenerationRow[];
  onForge: (req: RunRequest) => void;
  forging?: boolean;
  composeSummary?: string | null;
}) {
  return (
    <ScrollView contentContainerStyle={st.body} keyboardShouldPersistTaps="handled" testID="studio-brief">
      <SectionTitle hint="Forge questionnaire">{title}</SectionTitle>
      <View style={st.row}>
        <Button label="All projects" tone="ghost" compact onPress={onProjects} testID="studio-back" />
        <Button label="View build" tone="secondary" compact onPress={onViewBuild} testID="studio-view-build" />
        <Button label="Forge cockpit" tone="ghost" compact onPress={onOpenCockpit} testID="studio-cockpit" a11yHint="Opens eras, the compose graph, and the cockpit console" />
      </View>
      {catalogLoading ? <Banner tone="idle" testID="studio-catalog-loading">Loading the forge catalog… You can keep editing the brief.</Banner> : null}
      {catalogError ? (
        <View>
          <Banner tone="bad" testID="studio-catalog-error">{catalogError}</Banner>
          <Button label="Retry catalog" tone="secondary" onPress={onRetryCatalog} testID="studio-retry-catalog" />
        </View>
      ) : null}
      {conflict ? (
        <View testID="studio-run-conflict">
          <Banner tone="warn">{`Forging this project cancels the build of ${conflict.title}.`}</Banner>
          <View style={st.row}>
            <Button label="Cancel the other build and forge this" onPress={conflict.onConfirm} testID="studio-confirm-forge" />
            <Button label="View the other build" tone="secondary" onPress={conflict.onView} testID="studio-view-other" />
            <Button label="Keep the other build" tone="ghost" onPress={conflict.onKeep} testID="studio-keep-other" />
          </View>
        </View>
      ) : null}
      <QuestionnaireFlow
        state={state}
        dispatch={dispatch}
        beats={beats}
        beatsLive={beatsLive}
        eras={eras}
        generations={generations}
        onForge={onForge}
        forging={forging}
        composeSummary={composeSummary}
      />
    </ScrollView>
  );
}

const st = StyleSheet.create({
  body: { padding: 16, paddingBottom: 48 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 8 },
});
