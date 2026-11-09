module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    // `three` (and other modern libs) ship ES2022 static class blocks. The
    // production `expo export` bundle fails to parse them unless this plugin
    // is explicitly enabled, so add it here. babel-preset-expo already wires
    // up react-native-worklets/reanimated automatically.
    plugins: ['@babel/plugin-transform-class-static-block'],
  };
};
