import msgpack
import zlib
from game.state import GameState


def dump_state(state: GameState) -> bytes:
    d = state.to_dict()
    packed = msgpack.packb(d, use_bin_type=True)
    return zlib.compress(packed, level=9)


def load_state(data: bytes) -> GameState:
    packed = zlib.decompress(data)
    d = msgpack.unpackb(packed, raw=False)
    return GameState.from_dict(d)
