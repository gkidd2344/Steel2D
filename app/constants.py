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
}

RESERVED_HUES = [0.0, 0.167, 0.333, 0.083, 0.05]
HUE_EXCLUSION_RADIUS = 0.08
