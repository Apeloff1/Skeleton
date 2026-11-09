'use strict';
// Stand-in for deep `react-native/Libraries/*` imports (e.g. codegenNativeComponent)
// when rendering through react-native-web in node tests.
function codegenNativeComponent(name) { return name; }
module.exports = codegenNativeComponent;
module.exports.default = codegenNativeComponent;
