import React from 'react';
import type { EmeraldStageProps } from './emeraldStageTypes';
export default function EmeraldCrawlerStage({fallback}: EmeraldStageProps) {
  // Native 3D runtime is independently gated; do not imply it is installed or qualified.
  return <>{fallback}</>;
}
