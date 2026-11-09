from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from gameforge.enterprise.auth import Principal, get_principal
from gameforge.math_exocortex.hub import MathExocortex

router = APIRouter(prefix="/math", tags=["math-exocortex"])
_MATH: Dict[str, MathExocortex] = {}


def _m(uid: str) -> MathExocortex:
    if uid not in _MATH:
        _MATH[uid] = MathExocortex()
    return _MATH[uid]


class CalcBody(BaseModel):
    expr: str


class SheetBody(BaseModel):
    addr: str
    value: Any
    sheet: str = "default"


class SymbolicBody(BaseModel):
    action: str
    expr: Optional[str] = None
    names: Optional[str] = None
    var: str = "x"
    n: int = 1
    rows: Optional[List[List[Any]]] = None


class PowSumBody(BaseModel):
    numbers: List[float]
    chunk_size: int = 8


class PowMapBody(BaseModel):
    items: List[Any]
    map_expr: str
    chunk_size: int = 5


class BudgetBody(BaseModel):
    side: str
    category: str
    amount: float
    note: str = ""


class ForecastBody(BaseModel):
    progress_pct: float
    days_elapsed: float
    historical_daily_rates: Optional[List[float]] = None
    weather_penalty: float = 0.0
    energy: float = 0.55


class TaskBody(BaseModel):
    task_id: str
    duration_days: float = 1.0


class DepBody(BaseModel):
    before: str
    after: str


@router.get("/status")
async def status(principal: Principal = Depends(get_principal)):
    return _m(principal.user_id).status()


@router.post("/calc")
async def calc(req: CalcBody, principal: Principal = Depends(get_principal)):
    return _m(principal.user_id).calc(req.expr)


@router.post("/sheet/set")
async def sheet_set(req: SheetBody, principal: Principal = Depends(get_principal)):
    return _m(principal.user_id).sheet_set(req.addr, req.value, req.sheet)


@router.get("/sheet/get")
async def sheet_get(addr: str, sheet: str = "default", principal: Principal = Depends(get_principal)):
    return _m(principal.user_id).sheet_get(addr, sheet)


@router.post("/symbolic")
async def symbolic(req: SymbolicBody, principal: Principal = Depends(get_principal)):
    kw = {k: v for k, v in req.model_dump().items() if k != "action" and v is not None}
    return _m(principal.user_id).symbolic(req.action, **kw)


@router.post("/pow/sum")
async def pow_sum(req: PowSumBody, principal: Principal = Depends(get_principal)):
    return _m(principal.user_id).pow_sum(req.numbers, req.chunk_size)


@router.post("/pow/map")
async def pow_map(req: PowMapBody, principal: Principal = Depends(get_principal)):
    return _m(principal.user_id).pow_map(req.items, req.map_expr, req.chunk_size)


@router.get("/pow/status")
async def pow_status(principal: Principal = Depends(get_principal)):
    return _m(principal.user_id).pow_status()


@router.post("/budget")
async def budget_add(req: BudgetBody, principal: Principal = Depends(get_principal)):
    m = _m(principal.user_id)
    if req.side == "income":
        m.budget.add_income(req.category, req.amount, req.note)
    else:
        m.budget.add_expense(req.category, req.amount, req.note)
    return m.budget_summary()


@router.get("/budget")
async def budget_get(principal: Principal = Depends(get_principal)):
    return _m(principal.user_id).budget_summary()


@router.post("/graph/task")
async def graph_task(req: TaskBody, principal: Principal = Depends(get_principal)):
    _m(principal.user_id).graph.add_task(req.task_id, req.duration_days)
    return {"ok": True}


@router.post("/graph/dep")
async def graph_dep(req: DepBody, principal: Principal = Depends(get_principal)):
    _m(principal.user_id).graph.add_dep(req.before, req.after)
    return {"ok": True}


@router.get("/graph/critical_path")
async def critical_path(principal: Principal = Depends(get_principal)):
    return _m(principal.user_id).critical_path()


@router.post("/forecast")
async def forecast(req: ForecastBody, principal: Principal = Depends(get_principal)):
    return _m(principal.user_id).forecast_completion(**req.model_dump())


@router.post("/formal")
async def formal(statement: str, principal: Principal = Depends(get_principal)):
    return _m(principal.user_id).formal_prove(statement)


class LeanBody(BaseModel):
    statement: str
    context: str = ""
    tactic: Optional[str] = None


class ScaleWeightBody(BaseModel):
    scale_id: str
    label: str
    mass: str
    arm: str
    side: str = "left"


class ScaleIdBody(BaseModel):
    scale_id: str


@router.post("/sympy/init")
async def sympy_init(names: str = "x y z t n", principal: Principal = Depends(get_principal)):
    return _m(principal.user_id).init_sympy(symbol_names=names)


@router.get("/sympy/init_code")
async def sympy_init_code(principal: Principal = Depends(get_principal)):
    return _m(principal.user_id).sympy_init_code()


@router.post("/lean/prove")
async def lean_prove(req: LeanBody, principal: Principal = Depends(get_principal)):
    return _m(principal.user_id).lean_prove(req.statement, context=req.context, tactic=req.tactic)


@router.get("/lean/status")
async def lean_status(principal: Principal = Depends(get_principal)):
    return _m(principal.user_id).lean_status()


@router.post("/lean/template/{name}")
async def lean_template(name: str, tactic: Optional[str] = None, principal: Principal = Depends(get_principal)):
    return _m(principal.user_id).lean_template(name, tactic=tactic)


@router.post("/scale/create")
async def scale_create(principal: Principal = Depends(get_principal)):
    return _m(principal.user_id).scale_create()


@router.post("/scale/weight")
async def scale_weight(req: ScaleWeightBody, principal: Principal = Depends(get_principal)):
    return _m(principal.user_id).scale_add_weight(req.scale_id, req.label, req.mass, req.arm, req.side)


@router.post("/scale/evaluate")
async def scale_eval(req: ScaleIdBody, principal: Principal = Depends(get_principal)):
    return _m(principal.user_id).scale_evaluate(req.scale_id)


@router.get("/logs")
async def math_logs(tier: Optional[str] = None, n: int = 50, principal: Principal = Depends(get_principal)):
    return _m(principal.user_id).logs(tier=tier, n=n)


@router.get("/tools")
async def math_tools(principal: Principal = Depends(get_principal)):
    return _m(principal.user_id).tools()
