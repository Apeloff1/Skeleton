import type React from 'react';
import { ErrorBoundary } from '../../components/ErrorBoundary';
import type { ThemeColors } from '../../constants/themes';

// Compile-time sentinels for shared contracts that are consumed by hub.tsx.
// These values are never executed; `tsc --noEmit` is the regression gate.
type ErrorBoundaryProps = React.ComponentProps<typeof ErrorBoundary>;

type Assert<T extends true> = T;
type HasCard = Assert<'card' extends keyof ThemeColors ? true : false>;
type HasOnError = Assert<'onError' extends keyof ErrorBoundaryProps ? true : false>;

type _SharedUiContracts = HasCard | HasOnError;
export type { _SharedUiContracts };
