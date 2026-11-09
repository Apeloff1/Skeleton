import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/LanguageTrack/LanguageTrackModal'), 'LanguageTrackRoute', 'LanguageTrackModal');
