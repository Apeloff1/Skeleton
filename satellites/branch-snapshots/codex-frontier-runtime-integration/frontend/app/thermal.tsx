import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/ThermalMonitor/ThermalMonitorModal'), 'ThermalRoute', 'ThermalMonitorModal');
