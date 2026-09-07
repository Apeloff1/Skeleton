def create_app() -> Any:
    """Create and configure the FastAPI application."""
    fastapi = _get_fastapi()
    app = fastapi.FastAPI(
        title="Skeleton API",
        version="16.0.0",
        description="AI game engine / agent orchestration framework",
    )

    from skeleton.api.routes import router
    from skeleton.api.gameforge_routes import router as gameforge_router
    app.include_router(router, prefix="/api/v1")
    app.include_router(gameforge_router, prefix="/api/v1")

    @app.on_event("startup")
    async def startup():
        state = get_state()
        if state.genesis is None:
            from skeleton.genesis import Genesis
            state.wire_from_genesis(Genesis(seed=42).boot())

    @app.get("/")
    async def root():
        state = get_state()
        return {
            "name": "Skeleton",
            "version": "16.0.0",
            "status": "running",
            "jeeves_provider": state.jeeves.provider_name if state.jeeves else None,
        }

    @app.get("/cortex/status")
    async def cortex_status():
        from skeleton.cortex import live
        return live.status()

    return app
