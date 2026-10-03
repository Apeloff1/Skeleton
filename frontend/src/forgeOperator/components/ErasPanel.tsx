/**
 * Thin eras screen — reuses skeletonForge EraViewer over forgeOperator catalog data.
 */
import React from 'react';
import EraViewer from '../../skeletonForge/components/EraViewer';
import type { EraRow } from '../types';

export interface ErasPanelProps {
  eras: EraRow[];
  loading: boolean;
  error: string | null;
  onReload: () => void;
  resultEra?: string | null;
  pinnedEra?: string | null;
  onUseInForge?: (era: string) => void;
  testID?: string;
}

export default function ErasPanel({
  eras,
  loading,
  error,
  onReload,
  resultEra,
  pinnedEra,
  onUseInForge,
  testID,
}: ErasPanelProps) {
  const [selected, setSelected] = React.useState<string | null>(null);
  return (
    <EraViewer
      eras={eras}
      loading={loading}
      error={error}
      onReload={onReload}
      resultEra={resultEra}
      pinnedEra={pinnedEra}
      selected={selected}
      onSelect={setSelected}
      onUseInForge={onUseInForge}
      testID={testID ?? 'operator-eras'}
    />
  );
}
