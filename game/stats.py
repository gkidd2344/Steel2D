import math
from typing import TYPE_CHECKING

from app.config import STAT_KEYS, HEALTH_SIZE_LOOKUP, SCALAR_WEIGHT_LOOKUP

if TYPE_CHECKING:
    from game.objects import PlayerObject, NPC


def stat_mod(stat_value: int) -> int:
    """
    Standard D&D ability score modifier: floor((stat - 10) / 2).

    Examples (pairs sharing the same modifier):
        4-5 → -3,  6-7 → -2,  8-9 → -1,  10-11 → 0,
        12-13 → +1,  14-15 → +2,  16-17 → +3,  18-19 → +4, …
    """
    return (stat_value - 10) // 2   # Python // is floor-division; handles negatives correctly


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
    """
    HP = ceil(multiplier × (size_bonus + con_bonus))

    Level always contributes: a higher level with the same Con and Size will
    always have more HP.
    """
    size_bonus = max(1, level * HEALTH_SIZE_LOOKUP.get(size, 2))
    con_bonus = level * stat_mod(con) if stat_mod(con) > 0 else (math.ceil(math.sqrt(level))) * stat_mod(con)
    return max(1, math.ceil(multiplier * (size_bonus + con_bonus)))


def effective_stat(entity, key: str) -> int:
    """Return base + equipment bonus + Stat Modifier buff modifiers."""
    base = entity.Stats.get(key, 0)
    equip = 0
    if hasattr(entity, "Equipment"):
        equip = sum(
            item.Stats.get(key, 0)
            for item in entity.Equipment.values()
            if item.Stats is not None
        )
    buff_mod = 0
    buffs = getattr(entity, "Buffs", [])
    if isinstance(buffs, list):
        for b in buffs:
            if b.get("Type") == "Stat Modifier" and b.get("Stat") == key:
                buff_mod += b.get("Value", 0)
    return base + equip + buff_mod


def default_attack_damage(combatant) -> int:
    """
    Unarmed attack: best of Str/Dex modifier + ceil(Level × 1.5).
    The stat modifier may be negative; total damage is at least 1.
    """
    dex  = combatant.Stats.get("Dex", 0)
    str_ = combatant.Stats.get("Str", 0)
    best_mod = stat_mod(max(dex, str_))
    return max(1, best_mod + math.ceil(combatant.Level * 1.5))


def calculate_damage(combatant, scalars, action) -> int:
    if action is None:
        return default_attack_damage(combatant)
    base = action.get("BaseDamage", 0)
    active_scalars = scalars or {}
    scalar_total = sum(
        math.ceil(
            stat_mod(combatant.Stats.get(stat, 0))
            * (1 + SCALAR_WEIGHT_LOOKUP.get(weight, 0))
        )
        for stat, weight in active_scalars.items()
    )
    return scalar_total + base


def apply_action(combatant, scalars, action, target, settings) -> int:
    from game.objects import NPC, PlayerObject
    hits        = (action or {}).get("Hits", 1)
    dmg_per_hit = calculate_damage(combatant, scalars, action)
    total       = dmg_per_hit * hits
    npc_to_player = (
        isinstance(combatant, NPC)
        and isinstance(target, PlayerObject)
        and total > 0
    )
    if npc_to_player:
        total = math.ceil(total * settings.enemy_damage_multiplier)
    return total
