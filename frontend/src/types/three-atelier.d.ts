declare module 'three' {
  class AtelierThreeObject { constructor(...args: any[]); [key: string]: any; }
  export class WebGLRenderer extends AtelierThreeObject {}
  export class Box3 extends AtelierThreeObject {}
  export class AnimationMixer extends AtelierThreeObject {}
  export class LoadingManager extends AtelierThreeObject {}
  export const LoopOnce: number;
  export const LoopRepeat: number;
}
declare module 'three/addons/loaders/GLTFLoader.js' {
  export class GLTFLoader {
    constructor(manager?: any);
    parse(data: ArrayBuffer, path: string, onLoad: (result: {scene:any;scenes:any[];animations:any[]}) => void, onError: (error: unknown)=>void): void;
  }
}
