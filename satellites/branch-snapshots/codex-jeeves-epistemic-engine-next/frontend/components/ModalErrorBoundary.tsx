/**
 * <ModalErrorBoundary> — class component that isolates errors from
 *  any modal mounted inside `<LazyModal>`. When the wrapped tree throws:
 *    • Shows the SOTA <ErrorState> UI inline.
 *    • Lets the user actually recover ("Try again" remounts a fresh subtree,
 *      "Close" pulls the rip-cord via onClose if provided).
 *    • Auto-logs to console with the modal name for fast triage.
 *
 *  Without this, any unhandled exception inside *one* of the 75 feature
 *  modals brings down the entire app — the user just sees a global
 *  "Something went wrong" with a non-functional retry. That's why the
 *  user reported "Galaxy Studio has errors. Try again doesn't work."
 */
import React from 'react';
import { View, StyleSheet } from 'react-native';
import { ErrorState } from './ui/ErrorState';
import theme from '../theme/tokens';

interface Props {
  children: React.ReactNode;
  /** Human-readable feature name (used in logs + error title). */
  name?: string;
  /** Called when the user taps "Close" — typically the modal's own onClose. */
  onClose?: () => void;
}
interface State {
  hasError: boolean;
  error: Error | null;
  /** Bumped on every retry — used as a `key` to force-remount the subtree. */
  resetKey: number;
}

export class ModalErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false, error: null, resetKey: 0 };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
     
    console.error(`[ModalErrorBoundary:${this.props.name || 'unknown'}]`, error, info?.componentStack);
  }

  retry = () => {
    this.setState(prev => ({
      hasError: false,
      error: null,
      resetKey: prev.resetKey + 1,
    }));
  };

  close = () => {
    this.setState({ hasError: false, error: null }, () => {
      this.props.onClose?.();
    });
  };

  render() {
    if (this.state.hasError) {
      return (
        <View style={styles.fallback}>
          <ErrorState
            title={`${this.props.name || 'This feature'} hit a snag`}
            message="We caught the error before it could affect the rest of the app. You can retry, close this and pick another feature, or copy the details to share with us."
            error={this.state.error}
            onRetry={this.retry}
            fallbackAction={this.props.onClose ? { label: 'Close', onPress: this.close } : undefined}
          />
        </View>
      );
    }
    // Force a clean remount when retry is pressed by changing the key.
    return <React.Fragment key={this.state.resetKey}>{this.props.children}</React.Fragment>;
  }
}

const styles = StyleSheet.create({
  fallback: {
    flex: 1,
    backgroundColor: theme.colors.bg,
    justifyContent: 'center',
    alignItems: 'center',
    padding: theme.spacing.lg,
  },
});

export default ModalErrorBoundary;
