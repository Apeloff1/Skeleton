import AsyncStorage from '@react-native-async-storage/async-storage';
import { WorkbenchStore } from './WorkbenchStore';

// Both chat and workbench use one writer for the same local records.
export const workbenchStore = new WorkbenchStore(AsyncStorage);
