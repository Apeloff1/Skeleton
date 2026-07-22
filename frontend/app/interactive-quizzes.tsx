import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/InteractiveQuizzes/InteractiveQuizzesModal'), 'InteractiveQuizzesRoute', 'InteractiveQuizzesModal');
