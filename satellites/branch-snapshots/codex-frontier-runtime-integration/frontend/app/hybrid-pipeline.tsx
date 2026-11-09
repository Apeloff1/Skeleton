import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/HybridPipeline/HybridPipelineModal'), 'HybridPipelineRoute', 'HybridPipelineModal');
