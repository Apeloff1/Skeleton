import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/ImmersiveLearning/ImmersiveLearningModal'), 'ImmersiveLearningRoute', 'ImmersiveLearningModal');
