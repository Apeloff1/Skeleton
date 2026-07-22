import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/ImmersiveLearning/ImmersiveLearningModal'), 'ImmersiveLearningRoute', 'ImmersiveLearningModal');
