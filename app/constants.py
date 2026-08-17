BASE_CELL_PX = 64
ZOOM_MIN = 0.25
ZOOM_MAX = 4.0
ZOOM_STEP = 0.1
DEFAULT_PORT = 5000
POLL_INTERVAL_MS = 50
FPS_MS = 16

PALETTE = {
    "bg":       "#0d0d14",
    "card":     "#16162a",
    "card2":    "#1e1e38",
    "rest":     "#1B3A1B",
    "fight":    "#3B1919",
    "border":   "#2e2e4a",
    "accent":   "#2f7ee0",
    "danger":   "#cc2222",
    "success":  "#22aa22",
    "warning":  "#cc8800",
    "muted":    "#666680",
    "fg":       "#e6e6f0",
    "fg_dim":   "#999ab0",
    "tile":     "#ffffff",
    "grid":     "#1a1a1a",
    "canvas_bg":"#000000",
}

FONTS = {
    "title":      ("Segoe UI", 24, "bold"),
    "heading":    ("Segoe UI", 16, "bold"),
    "sub":        ("Segoe UI", 13, "bold"),
    "body":       ("Segoe UI", 12),
    "small":      ("Segoe UI", 10),
    "mono":       ("Consolas", 11),
    "chat":       ("Segoe UI", 11),
    "icon":       ("Segoe UI", 18),
    "form_label": ("Segoe UI", 12, "bold"),  # bold white labels in dialogs
}

TAG_COLOURS = {
    "normal":         "#e6e6f0",
    "yell":           "#f07060",   # salmon
    "whisper_out":    "#9090cc",
    "whisper_in":     "#9090cc",
    "system":         "#888888",
    "error":          "#cc3333",
    "combat_damage":  "#ff4444",   # red — damage numbers
    "combat_heal":    "#44ff88",   # green — heal numbers
    "combat_fizzle":  "#888888",   # grey — missed / fizzled
}

DM_CHAT_COLOR   = "#ff9500"   # orange for [DM] display in chat
YELL_CHAT_COLOR = "#f07060"   # salmon for /y

EQUIPMENT_SLOTS = {
    1: "Head",
    2: "Chest",
    3: "Legs",
    4: "Feet",
    5: "Ring",
    6: "Trinket",
    7: "Main Hand",
    8: "Off Hand",
    9: "Throwable",
}

THROWABLE_SLOT = 9

RESERVED_HUES = [0.0, 0.167, 0.333, 0.083, 0.05]
HUE_EXCLUSION_RADIUS = 0.08

# ── Player colour palette ─────────────────────────────────────────────────────
# Hues reserved for game elements that must stay visually distinct from players:
# NPC red/green, Item + DM orange, yell salmon, whisper blue/purple, etc.
PLAYER_RESERVED_HUES = [
    0.000,  # red (NPC hostile)
    0.030,  # salmon / yell
    0.050,  # red-orange (door-ish)
    0.080,  # orange (DM chat, Item)
    0.110,  # orange-yellow
    0.167,  # yellow
    0.333,  # green (NPC friendly)
    0.600,  # cyan-blue area
    0.650,  # blue (whisper)
    0.700,  # blue-purple
    0.750,  # purple
    0.800,  # purple-magenta
]
PLAYER_HUE_EXCLUSION = 0.06   # minimum hue distance from any reserved hue
PLAYER_COLOR_SAT = 0.85       # always high saturation — never washed out
PLAYER_COLOR_VAL = 1.0        # always full brightness — never dark
_PLAYER_HUE_STEPS = 72        # 5-degree steps around the wheel


def hue_to_player_hex(h: float) -> str:
    """Convert a hue to the canonical player colour at that hue."""
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(h, PLAYER_COLOR_SAT, PLAYER_COLOR_VAL)
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def player_palette_hues(exclusion: float = None) -> list:
    """Hues eligible for player colours, in wheel order.

    Single source of truth shared by the server's random colour assignment and
    the DM's manual colour picker, so both offer exactly the same options.
    """
    excl = PLAYER_HUE_EXCLUSION if exclusion is None else exclusion
    out = []
    for i in range(_PLAYER_HUE_STEPS):
        h = i / _PLAYER_HUE_STEPS
        if any(min(abs(h - r), 1.0 - abs(h - r)) < excl
               for r in PLAYER_RESERVED_HUES):
            continue
        out.append(h)
    return out


def player_palette(exclusion: float = None) -> list:
    """Hex colours eligible for players (same set the server randomises from)."""
    return [hue_to_player_hex(h) for h in player_palette_hues(exclusion)]
