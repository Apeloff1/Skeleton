import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/AIPipeline/AIPipelineModal'), 'AIPipelineRoute', 'AIPipelineModal');
