"""Read-only Mirror Room Observatory API.

The route exposes the live evidence projection and governed logical file tree.
It cannot start learning, mutate candidates, approve promotion, or change
production behavior.
"""

from fastapi import APIRouter, Response

from skeleton.learning.mirror_room.observability import (
    get_default_observatory,
    mirror_room_file_tree,
)


router = APIRouter(prefix="/api/mirror-room", tags=["mirror-room"])


@router.get("/status")
async def mirror_room_status(response: Response) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    return get_default_observatory().snapshot()


@router.get("/file-tree")
async def mirror_room_tree(response: Response) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    return dict(mirror_room_file_tree())


@router.get("/observatory")
async def mirror_room_observatory(response: Response) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    return {
        "status": get_default_observatory().snapshot(),
        "file_tree": dict(mirror_room_file_tree()),
    }


__all__ = ["router"]
