declare module 'three' {
  class AnyThree {
    constructor(...args: any[]);
    [key: string]: any;
  }

  export class BufferGeometry extends AnyThree {}
  export class BoxGeometry extends BufferGeometry {}
  export class CircleGeometry extends BufferGeometry {}
  export class ConeGeometry extends BufferGeometry {}
  export class CylinderGeometry extends BufferGeometry {}
  export class SphereGeometry extends BufferGeometry {}
  export class TorusGeometry extends BufferGeometry {}

  export class Color extends AnyThree {}
  export class Fog extends AnyThree {}
  export class Group extends AnyThree {}
  export class Scene extends AnyThree {}
  export class Mesh extends AnyThree {}
  export class MeshStandardMaterial extends AnyThree {}
  export class ShaderMaterial extends AnyThree {}
  export class PerspectiveCamera extends AnyThree {}
  export class HemisphereLight extends AnyThree {}
  export class DirectionalLight extends AnyThree {}
  export class GridHelper extends AnyThree {}
  export class Raycaster extends AnyThree {}
  export class Vector2 extends AnyThree {}
  export class Vector3 extends AnyThree {}
  export class Spherical extends AnyThree {}

  export const BackSide: any;
  export const SRGBColorSpace: any;
  export const ACESFilmicToneMapping: any;
  export const PCFSoftShadowMap: any;
}

declare module 'expo-three' {
  export class Renderer {
    constructor(options?: any);
    [key: string]: any;
  }
}
