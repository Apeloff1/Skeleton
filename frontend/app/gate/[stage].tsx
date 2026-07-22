import React from 'react';
import GateStage from '../../src/components/GateStage';

// Dynamic gate route — /gate/<stage>?build=<id> renders any gate by key
// (fine_tuning, intricacy, detail, quality_enhancement, fidelity, super_sampling,
//  production_grade, consumer_quality, approval, consensus, …).
export default function DynamicGatePage() {
  return <GateStage />;
}
