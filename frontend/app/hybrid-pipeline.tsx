import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/HybridPipeline/HybridPipelineModal'), 'HybridPipelineRoute', 'HybridPipelineModal');
