"""
╔══════════════════════════════════════════════════════════════════════════════╗
║             TEXT-TO-ECONOMY PIPELINE v15.5 - AI-POWERED ECONOMICS            ║
║                                                                              ║
║  Generate game economy systems with LLM integration:                         ║
║  • AI-designed currency systems                                              ║
║  • Intelligent market/trading mechanics                                      ║
║  • Balanced reward systems                                                   ║
║  • Ethical monetization models                                               ║
║  • Smart resource sinks & faucets                                            ║
║  • AI-powered inflation control                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from enum import Enum
import uuid
import random

# Import LLM service
from services.game_llm_service import get_game_llm_service

router = APIRouter(prefix="/api/economy", tags=["Text-to-Economy v15.5"])


# ============================================================================
# ENUMS & TYPE DEFINITIONS
# ============================================================================

class CurrencyType(str, Enum):
    SOFT = "soft"  # Earned through gameplay
    HARD = "hard"  # Premium/purchased
    HYBRID = "hybrid"
    REPUTATION = "reputation"
    CRAFTING = "crafting"
    SEASONAL = "seasonal"


class MarketType(str, Enum):
    NPC_VENDOR = "npc_vendor"
    AUCTION_HOUSE = "auction_house"
    PLAYER_TRADING = "player_trading"
    EXCHANGE = "exchange"
    BLACK_MARKET = "black_market"


class MonetizationType(str, Enum):
    FREE_TO_PLAY = "free_to_play"
    PREMIUM = "premium"
    SUBSCRIPTION = "subscription"
    BATTLE_PASS = "battle_pass"
    COSMETIC_ONLY = "cosmetic_only"
    PAY_TO_WIN = "pay_to_win"  # Not recommended!


class SinkType(str, Enum):
    REPAIR_COSTS = "repair_costs"
    CONSUMABLES = "consumables"
    TAXES = "taxes"
    UPGRADES = "upgrades"
    COSMETICS = "cosmetics"
    GAMBLING = "gambling"


# ============================================================================
# REQUEST MODELS
# ============================================================================

class CurrencyRequest(BaseModel):
    currency_name: str
    currency_type: CurrencyType = CurrencyType.SOFT
    initial_balance: int = Field(100, ge=0)
    max_cap: Optional[int] = None
    decimal_places: int = Field(0, ge=0, le=4)


class MarketRequest(BaseModel):
    market_name: str
    market_type: MarketType = MarketType.NPC_VENDOR
    dynamic_pricing: bool = True
    transaction_fee_percent: float = Field(5.0, ge=0.0, le=50.0)
    supply_demand: bool = True


class RewardBalancingRequest(BaseModel):
    activity_name: str
    difficulty: Literal["trivial", "easy", "medium", "hard", "extreme"] = "medium"
    time_investment_minutes: int = Field(15, ge=1, le=480)
    repeatable: bool = True
    daily_limit: Optional[int] = None


class MonetizationRequest(BaseModel):
    game_name: str
    monetization_type: MonetizationType = MonetizationType.FREE_TO_PLAY
    include_battle_pass: bool = False
    cosmetic_focus: bool = True


class EconomyBalanceRequest(BaseModel):
    economy_name: str
    target_inflation_rate: float = Field(0.02, ge=-0.1, le=0.2)
    faucets: List[str] = []
    sinks: List[SinkType] = []
    monitoring_enabled: bool = True


# ============================================================================
# ECONOMY GENERATOR
# ============================================================================

class EconomyGenerator:
    """Advanced game economy generation engine."""

    @staticmethod
    def generate_currency(request: CurrencyRequest) -> Dict[str, Any]:
        """Generate a currency system."""
        return {
            "id": str(uuid.uuid4()),
            "name": request.currency_name,
            "type": request.currency_type.value,
            "config": {
                "initial_balance": request.initial_balance,
                "max_cap": request.max_cap,
                "decimal_places": request.decimal_places,
                "tradeable": request.currency_type != CurrencyType.HARD,
                "transferable": request.currency_type == CurrencyType.SOFT
            },
            "display": {
                "icon": f"{request.currency_name.lower()}_icon",
                "color": EconomyGenerator._get_currency_color(request.currency_type),
                "format": "{:,." + str(request.decimal_places) + "f}"
            },
            "earning_sources": EconomyGenerator._get_earning_sources(request.currency_type),
            "spending_sinks": EconomyGenerator._get_spending_sinks(request.currency_type)
        }

    @staticmethod
    def _get_currency_color(currency_type: CurrencyType) -> str:
        colors = {
            CurrencyType.SOFT: "#FFD700",
            CurrencyType.HARD: "#00BFFF",
            CurrencyType.HYBRID: "#9B59B6",
            CurrencyType.REPUTATION: "#2ECC71",
            CurrencyType.CRAFTING: "#E67E22",
            CurrencyType.SEASONAL: "#E91E63"
        }
        return colors.get(currency_type, "#FFFFFF")

    @staticmethod
    def _get_earning_sources(currency_type: CurrencyType) -> List[Dict[str, Any]]:
        sources = {
            CurrencyType.SOFT: [
                {"source": "quest_completion", "rate": "variable"},
                {"source": "enemy_drops", "rate": "per_kill"},
                {"source": "daily_login", "rate": "daily"},
                {"source": "achievements", "rate": "one_time"}
            ],
            CurrencyType.HARD: [
                {"source": "in_app_purchase", "rate": "purchase"},
                {"source": "battle_pass", "rate": "seasonal"},
                {"source": "promotional", "rate": "event"}
            ],
            CurrencyType.REPUTATION: [
                {"source": "faction_quests", "rate": "per_quest"},
                {"source": "daily_bounties", "rate": "daily"},
                {"source": "world_events", "rate": "event"}
            ]
        }
        return sources.get(currency_type, [])

    @staticmethod
    def _get_spending_sinks(currency_type: CurrencyType) -> List[Dict[str, Any]]:
        sinks = {
            CurrencyType.SOFT: [
                {"sink": "vendor_purchases", "type": "consumable"},
                {"sink": "repairs", "type": "maintenance"},
                {"sink": "fast_travel", "type": "convenience"},
                {"sink": "auction_fees", "type": "tax"}
            ],
            CurrencyType.HARD: [
                {"sink": "cosmetics", "type": "permanent"},
                {"sink": "boosters", "type": "temporary"},
                {"sink": "inventory_slots", "type": "permanent"}
            ]
        }
        return sinks.get(currency_type, [])

    @staticmethod
    def generate_market(request: MarketRequest) -> Dict[str, Any]:
        """Generate a market system."""
        return {
            "id": str(uuid.uuid4()),
            "name": request.market_name,
            "type": request.market_type.value,
            "config": {
                "dynamic_pricing": request.dynamic_pricing,
                "transaction_fee": request.transaction_fee_percent,
                "supply_demand_enabled": request.supply_demand
            },
            "pricing_model": {
                "base_price_multiplier": 1.0,
                "supply_impact": 0.3 if request.supply_demand else 0,
                "demand_impact": 0.3 if request.supply_demand else 0,
                "update_frequency": "hourly" if request.dynamic_pricing else "static"
            },
            "features": {
                "search": True,
                "filtering": True,
                "sorting": True,
                "price_history": request.market_type == MarketType.AUCTION_HOUSE,
                "buy_orders": request.market_type == MarketType.EXCHANGE,
                "sell_orders": True
            },
            "limits": {
                "max_listings": 50,
                "listing_duration_hours": 48,
                "min_price": 1,
                "max_price": 999999999
            }
        }

    @staticmethod
    def generate_reward_balancing(request: RewardBalancingRequest) -> Dict[str, Any]:
        """Generate reward balancing for an activity."""
        difficulty_multipliers = {
            "trivial": 0.5,
            "easy": 0.8,
            "medium": 1.0,
            "hard": 1.5,
            "extreme": 2.5
        }
        
        base_reward = request.time_investment_minutes * 10
        multiplier = difficulty_multipliers[request.difficulty]
        
        return {
            "id": str(uuid.uuid4()),
            "activity": request.activity_name,
            "difficulty": request.difficulty,
            "time_investment": request.time_investment_minutes,
            "rewards": {
                "currency": int(base_reward * multiplier),
                "xp": int(base_reward * multiplier * 0.8),
                "item_drop_chance": min(0.5, 0.1 * multiplier)
            },
            "limits": {
                "repeatable": request.repeatable,
                "daily_limit": request.daily_limit,
                "weekly_limit": request.daily_limit * 7 if request.daily_limit else None
            },
            "efficiency": {
                "currency_per_minute": (base_reward * multiplier) / request.time_investment_minutes,
                "xp_per_minute": (base_reward * multiplier * 0.8) / request.time_investment_minutes
            }
        }

    @staticmethod
    def generate_monetization(request: MonetizationRequest) -> Dict[str, Any]:
        """Generate monetization model."""
        return {
            "id": str(uuid.uuid4()),
            "game": request.game_name,
            "model": request.monetization_type.value,
            "features": {
                "battle_pass": {
                    "enabled": request.include_battle_pass,
                    "tiers": 100,
                    "free_track": True,
                    "premium_track": True,
                    "duration_days": 90
                } if request.include_battle_pass else None,
                "store": {
                    "enabled": True,
                    "cosmetic_only": request.cosmetic_focus,
                    "categories": ["skins", "emotes", "bundles", "currency_packs"]
                },
                "daily_deals": True,
                "limited_time_offers": True
            },
            "pricing_tiers": [
                {"name": "starter", "price": 0.99, "value": "100 gems"},
                {"name": "regular", "price": 4.99, "value": "600 gems"},
                {"name": "value", "price": 9.99, "value": "1400 gems"},
                {"name": "premium", "price": 24.99, "value": "4000 gems"},
                {"name": "ultimate", "price": 99.99, "value": "18000 gems"}
            ],
            "ethical_guidelines": {
                "no_loot_boxes": request.cosmetic_focus,
                "no_pay_to_win": request.monetization_type != MonetizationType.PAY_TO_WIN,
                "spending_limits": True,
                "age_gating": True,
                "clear_odds_display": True
            }
        }

    @staticmethod
    def generate_economy_balance(request: EconomyBalanceRequest) -> Dict[str, Any]:
        """Generate economy balancing system."""
        return {
            "id": str(uuid.uuid4()),
            "name": request.economy_name,
            "target_inflation": request.target_inflation_rate,
            "faucets": [
                {"name": f, "type": "faucet", "monitored": True}
                for f in request.faucets
            ],
            "sinks": [
                {"name": s.value, "type": "sink", "effectiveness": 0.5}
                for s in request.sinks
            ],
            "monitoring": {
                "enabled": request.monitoring_enabled,
                "metrics": [
                    "total_currency_supply",
                    "currency_velocity",
                    "average_player_wealth",
                    "gini_coefficient",
                    "sink_faucet_ratio"
                ],
                "alerts": [
                    {"condition": "inflation > 5%", "action": "increase_sinks"},
                    {"condition": "deflation > 2%", "action": "increase_faucets"}
                ]
            },
            "auto_balancing": {
                "enabled": True,
                "adjustment_frequency": "weekly",
                "max_adjustment": 0.1
            }
        }


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/overview")
async def get_overview():
    """Get overview of the Economy Pipeline."""
    return {
        "pipeline": "Text-to-Economy Pipeline v15.5",
        "description": "Generate game economy systems from natural language",
        "capabilities": [
            "Currency system design",
            "Market/trading mechanics",
            "Reward balancing",
            "Monetization models",
            "Economy balancing & monitoring"
        ],
        "currency_types": [c.value for c in CurrencyType],
        "market_types": [m.value for m in MarketType],
        "monetization_types": [m.value for m in MonetizationType]
    }


@router.post("/currency/generate")
async def generate_currency(request: CurrencyRequest):
    """Generate a currency system."""
    return {
        "success": True,
        "currency": EconomyGenerator.generate_currency(request)
    }


@router.post("/market/generate")
async def generate_market(request: MarketRequest):
    """Generate a market system."""
    return {
        "success": True,
        "market": EconomyGenerator.generate_market(request)
    }


@router.post("/rewards/generate")
async def generate_reward_balancing(request: RewardBalancingRequest):
    """Generate reward balancing."""
    return {
        "success": True,
        "rewards": EconomyGenerator.generate_reward_balancing(request)
    }


@router.post("/monetization/generate")
async def generate_monetization(request: MonetizationRequest):
    """Generate monetization model."""
    return {
        "success": True,
        "monetization": EconomyGenerator.generate_monetization(request)
    }


@router.post("/balance/generate")
async def generate_economy_balance(request: EconomyBalanceRequest):
    """Generate economy balancing system."""
    return {
        "success": True,
        "economy_balance": EconomyGenerator.generate_economy_balance(request)
    }



# ============================================================================
# AI-POWERED ENDPOINTS (LLM Integration)
# ============================================================================

class AIEconomyDesignRequest(BaseModel):
    """Request for AI-powered economy design"""
    game_type: str = Field(..., description="RPG, mobile, MMO, etc.")
    monetization_model: str = Field(default="free_to_play", description="free_to_play, premium, subscription")


class AIMonetizationRequest(BaseModel):
    """Request for AI-powered monetization strategy"""
    game_type: str = Field(..., description="Game genre/type")
    target_audience: str = Field(default="casual", description="casual, hardcore, all_ages")


@router.post("/ai/economy/design")
async def ai_design_economy(request: AIEconomyDesignRequest):
    """
    Design a complete game economy using AI (GPT-4o).
    Creates balanced currencies, pricing, and anti-inflation measures.
    """
    try:
        llm_service = get_game_llm_service()
        
        result = await llm_service.generate_economy_design(
            game_type=request.game_type,
            monetization_model=request.monetization_model
        )
        
        if result["success"]:
            return {
                "success": True,
                "economy_design": result["response"],
                "ai_generated": True,
                "model": "gpt-4o",
                "design_metadata": {
                    "game_type": request.game_type,
                    "monetization_model": request.monetization_model
                }
            }
        else:
            # Fallback to template generation
            fallback_request = CurrencySystemRequest()
            return {
                "success": True,
                "economy_design": EconomyGenerator.generate_currency_system(fallback_request),
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI economy design failed: {str(e)}")


@router.post("/ai/monetization/strategy")
async def ai_design_monetization(request: AIMonetizationRequest):
    """
    Design an ethical monetization strategy using AI.
    Creates fair monetization with player protection measures.
    """
    try:
        llm_service = get_game_llm_service()
        
        result = await llm_service.generate_monetization_strategy(
            game_type=request.game_type,
            target_audience=request.target_audience
        )
        
        if result["success"]:
            return {
                "success": True,
                "monetization_strategy": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            fallback_request = MonetizationRequest()
            return {
                "success": True,
                "monetization_strategy": EconomyGenerator.generate_monetization(fallback_request),
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI monetization design failed: {str(e)}")
