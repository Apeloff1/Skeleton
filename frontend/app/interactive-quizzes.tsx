import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/InteractiveQuizzes/InteractiveQuizzesModal'), 'InteractiveQuizzesRoute', 'InteractiveQuizzesModal');
