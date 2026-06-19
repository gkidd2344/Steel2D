import random
from game.state import CombatState, CombatTurn, MOVE_COST, ACTION_COST, TURN_THRESHOLD


def roll_initiative(combatant) -> int:
    dex_bonus = max(combatant.Stats.get("Dex", 0) - 20, 0)
    return dex_bonus + random.randint(1, 20)


def build_turn_queue(players: dict, npc_cells: list) -> list:
    """Build the initiative order.

    NPCs with TurnsAllowed > 1 receive multiple initiative rolls and
    appear multiple times in the queue (one slot per allowed turn).
    Players with an active "Agility" buff gain (Value) extra initiative
    rolls / slots.
    """
    turns = []

    for uid, player in players.items():
        extra = int(player.Buffs.get("Agility", {}).get("Value", 0)) if hasattr(player, "Buffs") else 0
        slots = 1 + extra
        for _ in range(slots):
            init = roll_initiative(player)
            turns.append(CombatTurn(
                combatant_type="player",
                id=uid,
                name=player.Name,
                initiative=init,
            ))

    for npc_id, npc in npc_cells:
        slots = max(1, getattr(npc, "TurnsAllowed", 1))
        for _ in range(slots):
            init = roll_initiative(npc)
            turns.append(CombatTurn(
                combatant_type="npc",
                id=npc_id,
                name=npc.Name,
                initiative=init,
            ))

    # Sort descending; ties are randomised by the shuffle-then-sort trick
    random.shuffle(turns)
    turns.sort(key=lambda t: t.initiative, reverse=True)
    return turns


def advance_turn(combat: CombatState) -> CombatTurn:
    if not combat.turn_queue:
        return None
    combat.current_index = (combat.current_index + 1) % len(combat.turn_queue)
    if combat.current_index == 0:
        combat.round_number += 1
    current = combat.turn_queue[combat.current_index]
    current.has_acted = False
    current.points_spent = 0.0
    return current


def remove_combatant(combat: CombatState, combatant_id: str) -> None:
    """Remove ALL slots belonging to combatant_id from the queue."""
    indices = [i for i, t in enumerate(combat.turn_queue) if t.id == combatant_id]
    for idx in sorted(indices, reverse=True):
        if idx < combat.current_index:
            combat.current_index -= 1
        combat.turn_queue.pop(idx)
    if combat.turn_queue:
        combat.current_index = combat.current_index % len(combat.turn_queue)
    else:
        combat.current_index = 0
