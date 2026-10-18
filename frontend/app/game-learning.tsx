import React from 'react';
import StudioLoginGate from '../src/auth/StudioLoginGate';
import GameLearningWorkspace from '../src/features/Jeeves/GameLearningWorkspace';

export default function GameLearningRoute() {
  return <StudioLoginGate title="Game learning studio" requireAuthenticated><GameLearningWorkspace /></StudioLoginGate>;
}
