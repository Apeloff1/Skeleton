# Dependency update policy

Frontend framework upgrades have a larger compatibility surface than ordinary runtime library updates. Dependabot therefore keeps routine version updates inside the current major line and separates the following production dependency families into dedicated groups:

- Expo: `expo`, `expo-*`, `@expo/*`
- React / React Native platform: `react`, `react-dom`, `react-native`, `react-native-*`, `@react-navigation/*`, `@react-native-community/*`, `@react-native-async-storage/*`
- General frontend runtime: remaining production dependencies
- Frontend development: development-only dependencies

This keeps framework updates independently reviewable and bisectable while preserving grouped minor/patch maintenance for lower-risk libraries. Security updates remain governed separately by Dependabot security-update behavior and are not blocked by the routine version-update grouping policy.

Do not recombine Expo, React Native, navigation, and the full production dependency graph into one routine version-update pull request unless the application is intentionally performing a coordinated platform upgrade with dedicated compatibility validation.
