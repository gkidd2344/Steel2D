import math
from typing import TYPE_CHECKING

from app.config import STAT_KEYS, HEALTH_SIZE_LOOKUP, SCALAR_WEIGHT_LOOKUP

if TYPE_CHECKING:
    from game.objects import PlayerObject, NPC


def max_individual(level: int) -> int:
    return 18 + level * 2


def max_total(level: int) -> int:
    return 70 + level * 3


def clamp_stats(stats: dict, level: int) -> dict:
    result = {k: max(0, min(stats.get(k, 0), max_individual(level))) for k in STAT_KEYS}
    while sum(result.values()) > max_total(level):
        for k in STAT_KEYS:
            if result[k] > 0:
                result[k] -= 1
                if sum(result.values()) <= max_total(level):
                    break
    return result


def calc_max_hp(size: str, level: int, con: int, multiplier: float) -> int:
    size_val = HEALTH_SIZE_LOOKUP.get(size, 4)
    con_bonus = max(con - 20, 0)
    return max(1, math.ceil(multiplier * (size_val + level * con_bonus)))


def effective_stat(entity, key: str) -> int:
    """Return base + equipment bonus + buff modifiers for any stat-bearing entity."""
    base = entity.Stats.get(key, 0)
    # Equipment bonus (PlayerObject only)
    equip = 0
    if hasattr(entity, "Equipment"):
        equip = sum(
            item.Stats.get(key, 0)
            for item in entity.Equipment.values()
            if item.Stats is not None
        )
    # Buff modifiers
    buffs = getattr(entity, "Buffs", {})
    buff_mod = buffs.get(key, {}).get("Value", 0) if key in buffs else 0
    if key == "Dex" and "Poison" in buffs:
        buff_mod -= 1
    if key == "Str" and "Burn" in buffs:
        buff_mod -= 1
    return base + equip + buff_mod


def default_attack_damage(combatant) -> int:
    dex = combatant.Stats.get("Dex", 0)
    str_ = combatant.Stats.get("Str", 0)
    return max(max(dex, str_) - 20, 0) + math.ceil(combatant.Level * 1.5)


def calculate_damage(combatant, scalars, action) -> int:
    if action is None:
        return default_attack_damage(combatant)
    base = action.get("BaseDamage", 0)
    active_scalars = scalars or {}
    scalar_total = sum(
        math.ceil(
            max(combatant.Stats.get(stat, 0) - 20, 0)
            * (1 + SCALAR_WEIGHT_LOOKUP.get(weight, 0))
        )
        for stat, weight in active_scalars.items()
    )
    return scalar_total + base


def apply_action(combatant, scalars, action, target, settings) -> int:
    from game.objects import NPC, PlayerObject
    hits = (action or {}).get("Hits", 1)
    dmg_per_hit = calculate_damage(combatant, scalars, action)
    total = dmg_per_hit * hits
    npc_to_player = (
        isinstance(combatant, NPC)
        and isinstance(target, PlayerObject)
        and total > 0
    )
    if npc_to_player:
        total = math.ceil(total * settings.enemy_damage_multiplier)
    return total
