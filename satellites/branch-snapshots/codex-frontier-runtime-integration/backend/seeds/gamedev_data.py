"""
Game Development Academy Tracks — Hyperscale
Unity, Unreal, Godot, WebGL, and game engine architecture tracks.
"""

def get_gamedev_tracks():
    """Return all game development tracks."""
    # Deferred import: academy_data is heavy; keep it out of module top-level
    # so importing this module at boot stays cheap (cold-start win).
    from seeds.academy_data import _lesson, _exercise, _module, _project, _assessment, _question
    return [
        # ═══════════════════════════════════════════════════════════
        # UNITY TRACK
        # ═══════════════════════════════════════════════════════════
        {
            "id": "unity", "name": "Unity Game Development", "icon": "game-controller",
            "color": "#222C37", "total_hours": 3780, "category": "gamedev",
            "description": "Master Unity from basics to publishing AAA-quality games. Covers C#, physics, shaders, networking, and optimization.",
            "prerequisites": ["csharp"], "certificate": "Unity Game Developer Professional",
            "modules": [
                _module("unity_basics", "Unity Fundamentals", "Editor, GameObjects, Components, Scenes", 40, [
                    _lesson("u_b1", "Unity Editor & GameObjects", "Interface, hierarchy, inspector, transform", 90, "beginner", ["unity", "editor"],
                        "# Unity Editor\n\n## Core Concepts\n```\nGameObject: Container for components\nComponent: Behavior or data attached to a GameObject\nTransform: Position, rotation, scale (every GO has one)\nScene: Collection of GameObjects\nPrefab: Reusable GameObject template\n```\n\n## Creating GameObjects in C#\n```csharp\nusing UnityEngine;\n\npublic class Spawner : MonoBehaviour\n{\n    public GameObject prefab;\n    public int count = 10;\n    \n    void Start()\n    {\n        for (int i = 0; i < count; i++)\n        {\n            Vector3 pos = Random.insideUnitSphere * 10f;\n            GameObject obj = Instantiate(prefab, pos, Quaternion.identity);\n            obj.name = $\"Object_{i}\";\n        }\n    }\n}\n```\n\n## Component Lifecycle\n```\nAwake()       → Called once when script instance loads\nOnEnable()    → Called when object becomes active\nStart()       → Called once before first Update\nFixedUpdate() → Physics step (fixed 0.02s intervals)\nUpdate()      → Once per frame\nLateUpdate()  → After all Update calls\nOnDisable()   → When object becomes inactive\nOnDestroy()   → When object is destroyed\n```",
                        "using UnityEngine;\n\npublic class Rotator : MonoBehaviour\n{\n    public float speed = 100f;\n    \n    void Update()\n    {\n        transform.Rotate(Vector3.up * speed * Time.deltaTime);\n    }\n}"),
                    _lesson("u_b2", "Input & Player Control", "New Input System, character controllers", 75, "beginner", ["input", "movement"],
                        "# Player Control\n\n## New Input System\n```csharp\nusing UnityEngine;\nusing UnityEngine.InputSystem;\n\npublic class PlayerController : MonoBehaviour\n{\n    public float moveSpeed = 5f;\n    public float jumpForce = 8f;\n    \n    private Rigidbody rb;\n    private Vector2 moveInput;\n    private bool isGrounded;\n    \n    void Awake() => rb = GetComponent<Rigidbody>();\n    \n    public void OnMove(InputAction.CallbackContext ctx)\n        => moveInput = ctx.ReadValue<Vector2>();\n    \n    public void OnJump(InputAction.CallbackContext ctx)\n    {\n        if (ctx.performed && isGrounded)\n            rb.AddForce(Vector3.up * jumpForce, ForceMode.Impulse);\n    }\n    \n    void FixedUpdate()\n    {\n        Vector3 move = new Vector3(moveInput.x, 0, moveInput.y) * moveSpeed;\n        rb.MovePosition(rb.position + move * Time.fixedDeltaTime);\n    }\n    \n    void OnCollisionEnter(Collision col)\n    {\n        if (col.gameObject.CompareTag(\"Ground\")) isGrounded = true;\n    }\n    void OnCollisionExit(Collision col)\n    {\n        if (col.gameObject.CompareTag(\"Ground\")) isGrounded = false;\n    }\n}\n```"),
                    _lesson("u_b3", "Physics & Collisions", "Rigidbodies, colliders, triggers, raycasting", 90, "intermediate", ["physics", "collisions"],
                        "# Unity Physics\n\n## Raycasting\n```csharp\nvoid Update()\n{\n    if (Input.GetMouseButtonDown(0))\n    {\n        Ray ray = Camera.main.ScreenPointToRay(Input.mousePosition);\n        if (Physics.Raycast(ray, out RaycastHit hit, 100f))\n        {\n            Debug.Log($\"Hit: {hit.collider.name} at {hit.point}\");\n            Instantiate(impactPrefab, hit.point, Quaternion.LookRotation(hit.normal));\n        }\n    }\n}\n```\n\n## Overlap & Trigger Detection\n```csharp\n// Area damage\nvoid Explode(Vector3 center, float radius, float damage)\n{\n    Collider[] hits = Physics.OverlapSphere(center, radius);\n    foreach (var hit in hits)\n    {\n        var health = hit.GetComponent<Health>();\n        if (health != null)\n        {\n            float dist = Vector3.Distance(center, hit.transform.position);\n            float falloff = 1f - (dist / radius);\n            health.TakeDamage(damage * falloff);\n        }\n        \n        var rb = hit.GetComponent<Rigidbody>();\n        if (rb != null)\n            rb.AddExplosionForce(damage * 10, center, radius);\n    }\n}\n```"),
                ],
                    _project("u_proj1", "3D Platformer", "Build a complete 3D platformer with collectibles and enemies",
                        "intermediate", 20, ["Player controller with jump", "3 levels with increasing difficulty", "Collectible coins and power-ups", "2 enemy types with AI", "UI: health, score, timer", "Save/load system"],
                        tags=["unity", "3d", "platformer"]),
                    _assessment("u_assess1", "Unity Fundamentals Assessment", [
                        _question("uq1", "What is called every physics step?", ["Update()", "FixedUpdate()", "LateUpdate()", "Start()"], "FixedUpdate()", 10),
                        _question("uq2", "What component provides physics simulation?", ["Collider", "Rigidbody", "Transform", "MeshRenderer"], "Rigidbody", 10),
                        _question("uq3", "Time.deltaTime gives...", ["Fixed timestep", "Time since last frame", "Total time", "Framerate"], "Time since last frame", 10),
                    ], 70),
                ),
                _module("unity_advanced", "Advanced Unity", "Shaders, networking, optimization, VFX", 60, [
                    _lesson("u_a1", "Shader Programming", "ShaderGraph, HLSL, custom shaders", 120, "advanced", ["shaders", "hlsl"],
                        "# Unity Shaders\n\n## Simple Unlit Shader\n```hlsl\nShader \"Custom/SimpleUnlit\"\n{\n    Properties\n    {\n        _MainTex (\"Texture\", 2D) = \"white\" {}\n        _Color (\"Color\", Color) = (1,1,1,1)\n    }\n    SubShader\n    {\n        Tags { \"RenderType\"=\"Opaque\" }\n        \n        Pass\n        {\n            HLSLPROGRAM\n            #pragma vertex vert\n            #pragma fragment frag\n            #include \"UnityCG.cginc\"\n            \n            struct v2f {\n                float4 pos : SV_POSITION;\n                float2 uv : TEXCOORD0;\n            };\n            \n            sampler2D _MainTex;\n            float4 _Color;\n            \n            v2f vert(appdata_base v) {\n                v2f o;\n                o.pos = UnityObjectToClipPos(v.vertex);\n                o.uv = v.texcoord.xy;\n                return o;\n            }\n            \n            fixed4 frag(v2f i) : SV_Target {\n                return tex2D(_MainTex, i.uv) * _Color;\n            }\n            ENDHLSL\n        }\n    }\n}\n```\n\n## Dissolve Effect\n```hlsl\n// In fragment shader:\nfloat noise = tex2D(_NoiseTex, i.uv).r;\nclip(noise - _DissolveAmount);\n\n// Edge glow\nfloat edge = smoothstep(_DissolveAmount, _DissolveAmount + _EdgeWidth, noise);\nfixed4 edgeColor = lerp(_EdgeColor, fixed4(0,0,0,0), edge);\nreturn baseColor + edgeColor;\n```"),
                    _lesson("u_a2", "Multiplayer & Networking", "Netcode for GameObjects, Mirror, client-server", 120, "advanced", ["networking", "multiplayer"],
                        "# Unity Networking\n\n## Netcode for GameObjects\n```csharp\nusing Unity.Netcode;\n\npublic class NetworkPlayer : NetworkBehaviour\n{\n    public NetworkVariable<int> health = new(100);\n    public NetworkVariable<Vector3> netPosition = new();\n    \n    void Update()\n    {\n        if (IsOwner)\n        {\n            // Client sends input\n            Vector3 move = new(Input.GetAxis(\"Horizontal\"), 0, Input.GetAxis(\"Vertical\"));\n            MoveServerRpc(move);\n        }\n        else\n        {\n            // Other clients interpolate\n            transform.position = Vector3.Lerp(\n                transform.position, netPosition.Value, Time.deltaTime * 10);\n        }\n    }\n    \n    [ServerRpc]\n    void MoveServerRpc(Vector3 input)\n    {\n        transform.Translate(input * 5f * Time.deltaTime);\n        netPosition.Value = transform.position;\n    }\n    \n    [ServerRpc]\n    public void TakeDamageServerRpc(int amount)\n    {\n        health.Value -= amount;\n        if (health.Value <= 0)\n            DieClientRpc();\n    }\n    \n    [ClientRpc]\n    void DieClientRpc()\n    {\n        // Play death animation on all clients\n        GetComponent<Animator>().SetTrigger(\"Die\");\n    }\n}\n```"),
                    _lesson("u_a3", "Performance Optimization", "Profiler, batching, LOD, object pooling", 90, "advanced", ["optimization", "profiling"],
                        "# Unity Optimization\n\n## Object Pooling\n```csharp\npublic class ObjectPool : MonoBehaviour\n{\n    public GameObject prefab;\n    public int initialSize = 20;\n    private Queue<GameObject> pool = new();\n    \n    void Start()\n    {\n        for (int i = 0; i < initialSize; i++)\n        {\n            var obj = Instantiate(prefab);\n            obj.SetActive(false);\n            pool.Enqueue(obj);\n        }\n    }\n    \n    public GameObject Get(Vector3 position, Quaternion rotation)\n    {\n        GameObject obj;\n        if (pool.Count > 0)\n            obj = pool.Dequeue();\n        else\n            obj = Instantiate(prefab);\n        \n        obj.transform.SetPositionAndRotation(position, rotation);\n        obj.SetActive(true);\n        return obj;\n    }\n    \n    public void Return(GameObject obj)\n    {\n        obj.SetActive(false);\n        pool.Enqueue(obj);\n    }\n}\n```\n\n## Tips\n```\n1. Use SRP Batcher for shaders\n2. Enable GPU Instancing\n3. LOD Groups for distant objects\n4. Texture atlasing to reduce draw calls\n5. Addressables for memory management\n6. Job System + Burst for CPU-heavy work\n7. Avoid GetComponent() in Update — cache references\n8. Use OverlapSphereNonAlloc instead of OverlapSphere\n```"),
                ],
                    _project("u_proj2", "Multiplayer FPS", "Build an online FPS with Unity Netcode",
                        "advanced", 40, ["Client-server architecture", "Weapon system with 3 guns", "Hit detection with lag compensation", "Scoreboard and match system", "Map with spawn points", "Voice chat integration"],
                        tags=["unity", "multiplayer", "fps"]),
                ),
            ],
        },
        # ═══════════════════════════════════════════════════════════
        # UNREAL ENGINE TRACK
        # ═══════════════════════════════════════════════════════════
        {
            "id": "unreal", "name": "Unreal Engine Development", "icon": "rocket",
            "color": "#313131", "total_hours": 4320, "category": "gamedev",
            "description": "Master Unreal Engine 5 with C++, Blueprints, Nanite, Lumen, and AAA production workflows.",
            "prerequisites": ["cpp"], "certificate": "Unreal Engine Developer",
            "modules": [
                _module("ue_basics", "UE5 Fundamentals", "Editor, Blueprints, Actors, Components", 50, [
                    _lesson("ue_b1", "UE5 Editor & Blueprints", "Level editor, Blueprint visual scripting", 90, "beginner", ["unreal", "blueprints"],
                        "# Unreal Engine 5\n\n## Core Architecture\n```\nUWorld → ULevel → AActor → UActorComponent\n\nAActor: Base class for all placeable objects\nAPawn: Actor that can be possessed by controller\nACharacter: Pawn with movement component\nAPlayerController: Controls a Pawn\n```\n\n## C++ Actor\n```cpp\n// MyActor.h\n#pragma once\n#include \"CoreMinimal.h\"\n#include \"GameFramework/Actor.h\"\n#include \"MyActor.generated.h\"\n\nUCLASS()\nclass MYGAME_API AMyActor : public AActor\n{\n    GENERATED_BODY()\n    \npublic:\n    AMyActor();\n    virtual void Tick(float DeltaTime) override;\n    \n    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = \"Config\")\n    float RotationSpeed = 100.f;\n    \n    UPROPERTY(VisibleAnywhere)\n    UStaticMeshComponent* MeshComp;\n    \nprotected:\n    virtual void BeginPlay() override;\n};\n\n// MyActor.cpp\nAMyActor::AMyActor()\n{\n    PrimaryActorTick.bCanEverTick = true;\n    MeshComp = CreateDefaultSubobject<UStaticMeshComponent>(TEXT(\"Mesh\"));\n    RootComponent = MeshComp;\n}\n\nvoid AMyActor::Tick(float DeltaTime)\n{\n    Super::Tick(DeltaTime);\n    AddActorLocalRotation(FRotator(0, RotationSpeed * DeltaTime, 0));\n}\n```"),
                    _lesson("ue_b2", "Character & Movement", "Character class, movement component, animation", 120, "intermediate", ["character", "movement"],
                        "# UE5 Character System\n\n```cpp\n// MyCharacter.h\nUCLASS()\nclass AMyCharacter : public ACharacter\n{\n    GENERATED_BODY()\n    \n    UPROPERTY(VisibleAnywhere)\n    UCameraComponent* CameraComp;\n    \n    UPROPERTY(VisibleAnywhere)\n    USpringArmComponent* SpringArm;\n    \n    UPROPERTY(EditAnywhere)\n    float SprintSpeed = 1200.f;\n    \n    UPROPERTY(EditAnywhere)\n    float WalkSpeed = 600.f;\n    \npublic:\n    AMyCharacter();\n    virtual void SetupPlayerInputComponent(UInputComponent* Input) override;\n    \n    void Move(const FInputActionValue& Value);\n    void Look(const FInputActionValue& Value);\n    void StartSprint();\n    void StopSprint();\n};\n\n// MyCharacter.cpp\nAMyCharacter::AMyCharacter()\n{\n    SpringArm = CreateDefaultSubobject<USpringArmComponent>(TEXT(\"SpringArm\"));\n    SpringArm->SetupAttachment(RootComponent);\n    SpringArm->TargetArmLength = 300.f;\n    SpringArm->bUsePawnControlRotation = true;\n    \n    CameraComp = CreateDefaultSubobject<UCameraComponent>(TEXT(\"Camera\"));\n    CameraComp->SetupAttachment(SpringArm);\n    \n    GetCharacterMovement()->MaxWalkSpeed = WalkSpeed;\n}\n\nvoid AMyCharacter::StartSprint()\n{\n    GetCharacterMovement()->MaxWalkSpeed = SprintSpeed;\n}\n```"),
                ],
                    _project("ue_proj1", "Third-Person Action Game", "Build a 3rd person game with UE5",
                        "intermediate", 30, ["Character with sprint/jump/dodge", "Melee combat with animations", "3 enemy types with behavior trees", "Nanite environment", "Lumen global illumination", "Save system"],
                        tags=["unreal", "action", "3d"]),
                ),
            ],
        },
        # ═══════════════════════════════════════════════════════════
        # GODOT TRACK
        # ═══════════════════════════════════════════════════════════
        {
            "id": "godot", "name": "Godot Engine", "icon": "game-controller",
            "color": "#478CBF", "total_hours": 2700, "category": "gamedev",
            "description": "Master Godot 4 with GDScript for 2D and 3D game development. Open-source and lightweight.",
            "prerequisites": [], "certificate": "Godot Game Developer",
            "modules": [
                _module("godot_basics", "Godot 4 Fundamentals", "Nodes, scenes, GDScript, signals", 30, [
                    _lesson("gd_b1", "Godot Editor & GDScript", "Scene tree, nodes, GDScript syntax", 75, "beginner", ["godot", "gdscript"],
                        "# Godot 4 & GDScript\n\n## Node System\n```\nNode (base) → Node2D → Sprite2D, CollisionShape2D...\n                    → CharacterBody2D, RigidBody2D...\n            → Node3D → MeshInstance3D, Camera3D...\n            → Control → Button, Label, Panel...\n```\n\n## GDScript\n```gdscript\nextends CharacterBody2D\n\n@export var speed := 200.0\n@export var jump_force := -400.0\n\nvar gravity := ProjectSettings.get_setting(\"physics/2d/default_gravity\")\n\nfunc _physics_process(delta: float) -> void:\n    # Gravity\n    if not is_on_floor():\n        velocity.y += gravity * delta\n    \n    # Jump\n    if Input.is_action_just_pressed(\"jump\") and is_on_floor():\n        velocity.y = jump_force\n    \n    # Movement\n    var direction := Input.get_axis(\"move_left\", \"move_right\")\n    velocity.x = direction * speed\n    \n    move_and_slide()\n\n# Signals\nfunc _on_area_2d_body_entered(body: Node2D) -> void:\n    if body.is_in_group(\"player\"):\n        queue_free()  # Destroy self (collectible)\n        body.add_score(10)\n```\n\n## Signals (Events)\n```gdscript\n# Define custom signal\nsignal health_changed(new_value: int)\nsignal died\n\nvar health: int = 100:\n    set(value):\n        health = clamp(value, 0, 100)\n        health_changed.emit(health)\n        if health <= 0:\n            died.emit()\n```"),
                    _lesson("gd_b2", "2D Game Systems", "Tilemaps, animations, particles, UI", 90, "beginner", ["2d", "tilemap"],
                        "# 2D Game Systems\n\n## State Machine\n```gdscript\nclass_name StateMachine extends Node\n\nvar current_state: State\nvar states: Dictionary = {}\n\nfunc _ready() -> void:\n    for child in get_children():\n        if child is State:\n            states[child.name.to_lower()] = child\n            child.state_machine = self\n    current_state = get_child(0) as State\n    current_state.enter()\n\nfunc transition_to(state_name: String) -> void:\n    var new_state = states.get(state_name.to_lower())\n    if new_state and new_state != current_state:\n        current_state.exit()\n        current_state = new_state\n        current_state.enter()\n\nfunc _physics_process(delta: float) -> void:\n    current_state.physics_update(delta)\n```\n\n## Animation Player\n```gdscript\n@onready var anim := $AnimationPlayer\n@onready var sprite := $Sprite2D\n\nfunc update_animation() -> void:\n    if velocity.length() > 0:\n        anim.play(\"run\")\n        sprite.flip_h = velocity.x < 0\n    else:\n        anim.play(\"idle\")\n    \n    if not is_on_floor():\n        anim.play(\"jump\" if velocity.y < 0 else \"fall\")\n```"),
                ],
                    _project("gd_proj1", "Metroidvania", "Build a 2D Metroidvania with Godot 4",
                        "intermediate", 25, ["Platformer character with wall jump", "Interconnected map with unlockable areas", "3 boss fights", "Inventory and ability system", "Tilemap-based level design", "Save/load with JSON"],
                        tags=["godot", "2d", "metroidvania"]),
                ),
            ],
        },
        # ═══════════════════════════════════════════════════════════
        # WEB GAME DEV TRACK
        # ═══════════════════════════════════════════════════════════
        {
            "id": "webgame", "name": "Web Game Development", "icon": "globe",
            "color": "#61DAFB", "total_hours": 2700, "category": "gamedev",
            "description": "Master browser-based game development with Canvas, WebGL, Three.js, and Phaser.",
            "prerequisites": ["javascript"], "certificate": "Web Game Developer",
            "modules": [
                _module("webgame_canvas", "HTML5 Canvas & Phaser", "2D rendering, sprites, game loops", 30, [
                    _lesson("wg_b1", "Canvas Game Loop", "RequestAnimationFrame, sprites, input", 75, "beginner", ["canvas", "game-loop"],
                        "# HTML5 Canvas Game\n\n```javascript\nconst canvas = document.getElementById('game');\nconst ctx = canvas.getContext('2d');\ncanvas.width = 800;\ncanvas.height = 600;\n\nclass Player {\n  constructor(x, y) {\n    this.x = x; this.y = y;\n    this.width = 32; this.height = 32;\n    this.speed = 5; this.dx = 0; this.dy = 0;\n  }\n  \n  update() {\n    this.x += this.dx * this.speed;\n    this.y += this.dy * this.speed;\n    // Bounds\n    this.x = Math.max(0, Math.min(canvas.width - this.width, this.x));\n    this.y = Math.max(0, Math.min(canvas.height - this.height, this.y));\n  }\n  \n  draw(ctx) {\n    ctx.fillStyle = '#00ff00';\n    ctx.fillRect(this.x, this.y, this.width, this.height);\n  }\n}\n\nconst player = new Player(400, 300);\nconst keys = {};\n\ndocument.addEventListener('keydown', e => keys[e.key] = true);\ndocument.addEventListener('keyup', e => keys[e.key] = false);\n\nfunction gameLoop() {\n  // Input\n  player.dx = (keys['d'] ? 1 : 0) - (keys['a'] ? 1 : 0);\n  player.dy = (keys['s'] ? 1 : 0) - (keys['w'] ? 1 : 0);\n  \n  // Update\n  player.update();\n  \n  // Render\n  ctx.fillStyle = '#1a1a2e';\n  ctx.fillRect(0, 0, canvas.width, canvas.height);\n  player.draw(ctx);\n  \n  requestAnimationFrame(gameLoop);\n}\n\ngameLoop();\n```"),
                ],
                    _project("wg_proj1", "Browser Arcade Game", "Build a complete browser game",
                        "beginner", 10, ["Canvas rendering", "Collision detection", "Score system", "Sound effects", "Mobile touch controls"],
                        tags=["web", "canvas", "game"]),
                ),
                _module("webgame_3d", "Three.js & WebGL", "3D rendering, shaders, physics", 40, [
                    _lesson("wg_3d1", "Three.js Fundamentals", "Scene, camera, renderer, meshes, lights", 90, "intermediate", ["threejs", "webgl"],
                        "# Three.js\n\n```javascript\nimport * as THREE from 'three';\nimport { OrbitControls } from 'three/examples/jsm/controls/OrbitControls';\n\n// Scene setup\nconst scene = new THREE.Scene();\nscene.background = new THREE.Color(0x1a1a2e);\n\nconst camera = new THREE.PerspectiveCamera(75, window.innerWidth/window.innerHeight, 0.1, 1000);\ncamera.position.set(0, 5, 10);\n\nconst renderer = new THREE.WebGLRenderer({ antialias: true });\nrenderer.setSize(window.innerWidth, window.innerHeight);\nrenderer.shadowMap.enabled = true;\ndocument.body.appendChild(renderer.domElement);\n\n// Controls\nconst controls = new OrbitControls(camera, renderer.domElement);\n\n// Lights\nconst sun = new THREE.DirectionalLight(0xffffff, 1);\nsun.position.set(5, 10, 5);\nsun.castShadow = true;\nscene.add(sun);\nscene.add(new THREE.AmbientLight(0x404040));\n\n// Ground\nconst ground = new THREE.Mesh(\n  new THREE.PlaneGeometry(20, 20),\n  new THREE.MeshStandardMaterial({ color: 0x228B22 })\n);\nground.rotation.x = -Math.PI / 2;\nground.receiveShadow = true;\nscene.add(ground);\n\n// Animated cube\nconst cube = new THREE.Mesh(\n  new THREE.BoxGeometry(1, 1, 1),\n  new THREE.MeshStandardMaterial({ color: 0xff6347 })\n);\ncube.position.y = 0.5;\ncube.castShadow = true;\nscene.add(cube);\n\n// Animation loop\nfunction animate() {\n  requestAnimationFrame(animate);\n  cube.rotation.y += 0.01;\n  cube.position.y = 0.5 + Math.sin(Date.now() * 0.002) * 0.3;\n  controls.update();\n  renderer.render(scene, camera);\n}\nanimate();\n```"),
                ],
                    _project("wg_proj2", "3D Web Experience", "Build an interactive 3D scene with Three.js",
                        "intermediate", 15, ["Custom shaders", "Physics with Cannon.js", "GLTF model loading", "Post-processing effects", "Responsive design"],
                        tags=["threejs", "3d", "webgl"]),
                ),
            ],
        },
    ]
