"""Supervisory orchestration for Night Shift and Idle Shift bot teams."""

from .model_gateway import ModelGateway, ModelRequestError
from .models import PlanItem, WorkerState
from .plan_api import PlanQueueAPI, PlanReadAPI, SquadPlanQueueAPI
from .plan_store import InMemoryPlanStore
from .secretary import SecretaryBot
from .shift_manager import SMBShiftManager
from .squads import SQUAD_ROLES, SQUAD_SIZE, SquadCoordinator, SquadLease, safe_squad_capacity

__all__ = [
    "InMemoryPlanStore",
    "ModelGateway",
    "ModelRequestError",
    "PlanItem",
    "PlanQueueAPI",
    "PlanReadAPI",
    "SQUAD_ROLES",
    "SQUAD_SIZE",
    "SecretaryBot",
    "SMBShiftManager",
    "SquadCoordinator",
    "SquadLease",
    "SquadPlanQueueAPI",
    "WorkerState",
    "safe_squad_capacity",
]
