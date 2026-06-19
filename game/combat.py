import random
from game.state import CombatState, CombatTurn


def roll_initiative(combatant) -> int:
    dex_bonus = max(combatant.Stats.get("Dex", 0) - 20, 0)
    return dex_bonus + random.randint(1, 20)


def build_turn_queue(players: dict, npc_cells: list) -> list:
    turns = []
    for uuid, player in players.items():
        init = roll_initiative(player)
        turns.append(CombatTurn(
            combatant_type="player",
            id=uuid,
            name=player.Name,
            initiative=init,
        ))
    for npc_id, npc in npc_cells:
        init = roll_initiative(npc)
        turns.append(CombatTurn(
            combatant_type="npc",
            id=npc_id,
            name=npc.Name,
            initiative=init,
        ))
    turns.sort(key=lambda t: t.initiative, reverse=True)
    random.shuffle(turns)  # randomise ties by shuffling then re-sorting
    turns.sort(key=lambda t: t.initiative, reverse=True)
    return turns


def advance_turn(combat: CombatState) -> CombatTurn:
    if not combat.turn_queue:
        return None
    combat.current_index = (combat.current_index + 1) % len(combat.turn_queue)
    if combat.current_index == 0:
        combat.round_number += 1
    current = combat.turn_queue[combat.current_index]
    current.has_moved = False
    current.has_acted = False
    return current


def remove_combatant(combat: CombatState, combatant_id: str) -> None:
    idx = next((i for i, t in enumerate(combat.turn_queue) if t.id == combatant_id), None)
    if idx is None:
        return
    if idx < combat.current_index:
        combat.current_index -= 1
    elif idx == combat.current_index:
        pass  # next element shifts in; index stays valid (or wraps)
    combat.turn_queue.pop(idx)
    if combat.turn_queue:
        combat.current_index = combat.current_index % len(combat.turn_queue)
    else:
        combat.current_index = 0
