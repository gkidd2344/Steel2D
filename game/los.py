import math
from typing import Tuple, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from game.state import GameState


def _bresenham(x0: int, y0: int, x1: int, y1: int):
    cells = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        cells.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy
    return cells


def has_los(state: "GameState", from_cell: Tuple[int, int], to_cell: Tuple[int, int], max_distance: int) -> bool:
    fx, fy = from_cell
    tx, ty = to_cell
    dist = math.sqrt((tx - fx) ** 2 + (ty - fy) ** 2)
    if dist > max_distance:
        return False
    path = _bresenham(fx, fy, tx, ty)
    for cell in path[1:-1]:
        if cell not in state.grid or not state.grid[cell].walkable:
            return False
    return True


def cells_in_range(origin: Tuple[int, int], action_range: int, state: "GameState", max_los: int) -> Set[Tuple[int, int]]:
    if action_range == 0:
        return {origin}
    if action_range == 1:
        ox, oy = origin
        return {(ox + dx, oy + dy) for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0))}
    result = set()
    ox, oy = origin
    for (x, y) in state.grid:
        dist = math.sqrt((x - ox) ** 2 + (y - oy) ** 2)
        if dist <= action_range and has_los(state, origin, (x, y), max_los):
            result.add((x, y))
    return result
