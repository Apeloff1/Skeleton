"""
Engine + API schema knowledge base.

Mongo collection: `engine_api_schemas`.

For each supported engine we record the canonical entry-point classes,
lifecycle methods, common subsystems, language bindings, and minimal
bootstrap snippet. Agents consume this when generating engine-targeted code.
"""
from __future__ import annotations
import hashlib, logging
from datetime import datetime, timezone

log = logging.getLogger("knowledge.engine_api")

ENGINES = [
    {
        "engine": "Unity", "version": "6.0", "language": "C#",
        "lifecycle": ["Awake","OnEnable","Start","FixedUpdate","Update","LateUpdate","OnDisable","OnDestroy"],
        "key_namespaces": ["UnityEngine","UnityEngine.UI","UnityEngine.Rendering","Unity.Entities","Unity.Mathematics","Unity.Burst","Unity.Jobs"],
        "render_pipeline": ["Built-in","URP","HDRP"],
        "input": "Input System package (preferred over legacy Input class)",
        "bootstrap": "using UnityEngine;\npublic class Boot : MonoBehaviour { void Start() { Debug.Log(\"Hello Unity 6\"); } }",
    },
    {
        "engine": "Unreal Engine", "version": "5.4", "language": "C++/Blueprint",
        "lifecycle": ["BeginPlay","Tick","EndPlay","OnConstruction","PostInitializeComponents"],
        "key_namespaces": ["Core","Engine","Slate","Niagara","Chaos","GameplayAbilities","EnhancedInput"],
        "render_pipeline": ["Lumen (default)","Path Tracer","Forward"],
        "input": "Enhanced Input subsystem with input mapping contexts",
        "bootstrap": "#include \"GameFramework/Actor.h\"\nclass APlayerActor : public AActor { virtual void BeginPlay() override; };",
    },
    {
        "engine": "Godot", "version": "4.3", "language": "GDScript/C#/C++",
        "lifecycle": ["_ready","_process","_physics_process","_input","_unhandled_input","_notification","_exit_tree"],
        "key_namespaces": ["Node","Node2D","Node3D","Control","RigidBody3D","CharacterBody3D","GPUParticles3D","Resource"],
        "render_pipeline": ["Forward+","Mobile","Compatibility"],
        "input": "InputMap + Input singleton; Action-based",
        "bootstrap": "extends Node\nfunc _ready(): print(\"Hello Godot 4.3\")",
    },
    {
        "engine": "Bevy", "version": "0.14", "language": "Rust",
        "lifecycle": ["Startup","PreUpdate","Update","PostUpdate","Render","Last"],
        "key_namespaces": ["bevy::prelude","bevy::ecs","bevy::render","bevy::ui","bevy::asset","bevy::input"],
        "render_pipeline": ["WGSL via wgpu"],
        "input": "Res<Input<KeyCode>> + EventReader<MouseMotion>",
        "bootstrap": "use bevy::prelude::*;\nfn main(){ App::new().add_plugins(DefaultPlugins).run(); }",
    },
    {
        "engine": "Phaser", "version": "3.85", "language": "JavaScript/TypeScript",
        "lifecycle": ["preload","create","update","shutdown"],
        "key_namespaces": ["Phaser.Scene","Phaser.GameObjects","Phaser.Physics.Arcade","Phaser.Input","Phaser.Tilemaps"],
        "render_pipeline": ["WebGL","Canvas fallback"],
        "input": "this.input.keyboard.createCursorKeys() / pointer",
        "bootstrap": "new Phaser.Game({ type: Phaser.AUTO, width: 800, height: 600, scene: { preload, create, update } });",
    },
    {
        "engine": "Three.js", "version": "r168", "language": "JavaScript/TypeScript",
        "lifecycle": ["init","animate (rAF loop)","resize","dispose"],
        "key_namespaces": ["THREE.Scene","THREE.PerspectiveCamera","THREE.WebGLRenderer","THREE.Mesh","THREE.Material","THREE.Loader"],
        "render_pipeline": ["WebGL2","WebGPU (preview)"],
        "input": "DOM event listeners; OrbitControls for camera",
        "bootstrap": "import * as THREE from 'three';\nconst s = new THREE.Scene();",
    },
    {
        "engine": "Babylon.js", "version": "7.x", "language": "TypeScript",
        "lifecycle": ["createScene","runRenderLoop","resize","dispose"],
        "key_namespaces": ["BABYLON.Engine","BABYLON.Scene","BABYLON.Camera","BABYLON.MeshBuilder","BABYLON.Material"],
        "render_pipeline": ["WebGPU (default)","WebGL2"],
        "input": "scene.onPointerObservable",
        "bootstrap": "const engine = new BABYLON.Engine(canvas, true);",
    },
    {
        "engine": "LÖVE", "version": "11.5", "language": "Lua",
        "lifecycle": ["love.load","love.update(dt)","love.draw","love.keypressed","love.quit"],
        "key_namespaces": ["love.graphics","love.audio","love.physics (Box2D)","love.filesystem"],
        "render_pipeline": ["OpenGL ES 2"],
        "input": "love.keyboard + love.mouse + love.touch",
        "bootstrap": "function love.load() print('Hello LÖVE') end",
    },
    {
        "engine": "Pygame", "version": "2.6", "language": "Python",
        "lifecycle": ["pygame.init","event-loop","clock.tick","pygame.quit"],
        "key_namespaces": ["pygame.display","pygame.sprite","pygame.mixer","pygame.event","pygame.font"],
        "render_pipeline": ["SDL2 software"],
        "input": "pygame.event.get() / pygame.key.get_pressed()",
        "bootstrap": "import pygame; pygame.init(); screen = pygame.display.set_mode((800,600))",
    },
    {
        "engine": "GameMaker", "version": "2024.x", "language": "GML",
        "lifecycle": ["Create","Step","Begin Step","End Step","Draw","Draw GUI","Destroy"],
        "key_namespaces": ["audio_*","draw_*","instance_*","event_*","buffer_*"],
        "render_pipeline": ["DirectX","OpenGL","Metal"],
        "input": "keyboard_check, mouse_check, gamepad_*",
        "bootstrap": "// Create Event\nspeed = 4; direction = 0;",
    },
    {
        "engine": "Cocos Creator", "version": "3.8", "language": "TypeScript",
        "lifecycle": ["onLoad","start","update","lateUpdate","onDestroy","onEnable","onDisable"],
        "key_namespaces": ["cc.Node","cc.Component","cc.Tween","cc.Sprite","cc.Animation"],
        "render_pipeline": ["WebGL2","GLES3","Metal","Vulkan"],
        "input": "cc.input.on(Input.EventType.TOUCH_START, fn)",
        "bootstrap": "@ccclass('Boot') export class Boot extends Component { start(){} }",
    },
    {
        "engine": "Defold", "version": "1.9", "language": "Lua",
        "lifecycle": ["init","final","update","on_message","on_input","on_reload"],
        "key_namespaces": ["go","vmath","gui","sound","physics"],
        "render_pipeline": ["OpenGL ES","Vulkan"],
        "input": "on_input(self, action_id, action)",
        "bootstrap": "function init(self) print('Hello Defold') end",
    },
    {
        "engine": "Construct 3", "version": "r400", "language": "Event-Sheet / JS",
        "lifecycle": ["OnStartOfLayout","Every Tick","OnEndOfLayout"],
        "key_namespaces": ["Sprite","Audio","Physics","Pathfinding"],
        "render_pipeline": ["WebGL"],
        "input": "Built-in Touch / Mouse / Keyboard objects",
        "bootstrap": "// Event sheet — On start of layout → Create object Player",
    },
    {
        "engine": "O3DE", "version": "23.10", "language": "C++/Python/Script Canvas",
        "lifecycle": ["OnInit","OnTick","OnShutdown"],
        "key_namespaces": ["AzCore","AzFramework","AzGameFramework","Atom"],
        "render_pipeline": ["Atom (PBR, ray-tracing)"],
        "input": "AzFramework::InputChannelEventListener",
        "bootstrap": "class GameSystemComponent : public AZ::Component { void Activate() override; };",
    },
    {
        "engine": "Stride", "version": "4.2", "language": "C#",
        "lifecycle": ["Start","Update","Cancel"],
        "key_namespaces": ["Stride.Engine","Stride.Graphics","Stride.Audio","Stride.Input"],
        "render_pipeline": ["Forward+","VR"],
        "input": "Input.IsKeyPressed(Keys.Space)",
        "bootstrap": "public class GameScript : SyncScript { public override void Update() {} }",
    },
    {
        "engine": "FNA / MonoGame", "version": "3.8.1", "language": "C#",
        "lifecycle": ["Initialize","LoadContent","Update","Draw","UnloadContent"],
        "key_namespaces": ["Microsoft.Xna.Framework","Microsoft.Xna.Framework.Graphics"],
        "render_pipeline": ["DirectX 11","OpenGL","Vulkan (FNA3D)"],
        "input": "Keyboard.GetState() / Mouse.GetState() / GamePad.GetState",
        "bootstrap": "public class Game1 : Game { protected override void Update(GameTime gt){} }",
    },
    {
        "engine": "libGDX", "version": "1.12", "language": "Java/Kotlin",
        "lifecycle": ["create","resize","render","pause","resume","dispose"],
        "key_namespaces": ["com.badlogic.gdx","com.badlogic.gdx.graphics","com.badlogic.gdx.scenes.scene2d"],
        "render_pipeline": ["OpenGL ES 3"],
        "input": "Gdx.input.isKeyPressed(Input.Keys.SPACE)",
        "bootstrap": "public class Game extends ApplicationAdapter { public void render(){} }",
    },
    {
        "engine": "Heaps.io", "version": "1.10", "language": "Haxe",
        "lifecycle": ["new (init)","update(dt)","render","onDispose"],
        "key_namespaces": ["h2d.Scene","h3d.scene","hxd.Res","hxd.Window"],
        "render_pipeline": ["OpenGL","DirectX","WebGL"],
        "input": "hxd.Key.isDown(K.SPACE)",
        "bootstrap": "class Game extends hxd.App { override function init(){} }",
    },
    {
        "engine": "PixiJS", "version": "8", "language": "TypeScript",
        "lifecycle": ["Application.init","ticker.add","destroy"],
        "key_namespaces": ["PIXI.Application","PIXI.Sprite","PIXI.Container","PIXI.Graphics","PIXI.Text"],
        "render_pipeline": ["WebGPU","WebGL2"],
        "input": "DOM events + sprite.interactive=true",
        "bootstrap": "const app = new Application(); await app.init({ background:'#1099bb' });",
    },
    {
        "engine": "OpenSiv3D", "version": "0.6", "language": "C++",
        "lifecycle": ["Main","System::Update"],
        "key_namespaces": ["s3d::Scene","s3d::Window","s3d::Input","s3d::TexturedQuad"],
        "render_pipeline": ["DirectX 11","Metal"],
        "input": "if(KeyA.pressed())",
        "bootstrap": "void Main(){ while(System::Update()){} }",
    },
]


def _eid(e): return "engine_" + hashlib.md5(e["engine"].encode()).hexdigest()[:14]


async def seed_engine_api(db) -> dict:
    try:
        await db.engine_api_schemas.create_index("id", unique=True)
        await db.engine_api_schemas.create_index("engine")
        await db.engine_api_schemas.create_index("language")
    except Exception:
        pass
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for e in ENGINES:
        doc = dict(e)
        doc["id"] = _eid(e)
        doc["indexed_at"] = now
        doc["tags"] = [doc["engine"].lower().replace(" ", "-"), doc["language"].lower(), "engine-schema"]
        try:
            r = await db.engine_api_schemas.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)
            if r.upserted_id is not None: inserted += 1
        except Exception: pass
    total = await db.engine_api_schemas.count_documents({})
    return {"inserted": inserted, "total": total, "engines": len(ENGINES)}
