# config.py - Structural config only: colors, layout dimensions, Ollama settings.
# No pattern lists. Intelligence lives in llm.py.

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODELS = ["qwen3.5:9b", "glm-4.7-flash:latest"]
OLLAMA_TIMEOUT = 120

SEARXNG_URL = "http://localhost:8888/search"

# --------------------------------------------------------------------------
# Cloud API providers (OpenAI-compatible)
# --------------------------------------------------------------------------
API_PROVIDERS: dict[str, dict] = {
    "minimax": {
        "base_url": "https://api.minimax.chat/v1",
        "default_model": "MiniMax-M2.5",
        # MiniMax built-in web search tool format
        "search_tool": {
            "type": "web_search",
            "web_search": {"enable": True, "search_mode": "performance_first"},
        },
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "kimi-k2-5-instruct",
        # Kimi built-in search (server-side execution)
        "search_tool": {
            "type": "builtin_function",
            "function": {"name": "$web_search"},
        },
    },
}

# Set by GUI/CLI at runtime; "ollama" means use local Ollama
ACTIVE_PROVIDER: str = "ollama"   # "ollama" | "minimax" | "kimi"
ACTIVE_API_KEY: str = ""
ACTIVE_API_MODEL: str = ""        # overrides provider default_model when set

# Category display config: color and pipeline order for layout/grouping.
# Category names must match exactly what the LLM is asked to return.
# Input/Output are special console columns placed at far-left and far-right.
NODE_CATEGORIES: dict[str, dict] = {
    "Input": {
        "color": "#1a6b2a",   # vivid green - user entry points
        "order": -1,           # leftmost column
    },
    "Loader": {
        "color": "#2b5278",
        "order": 0,
    },
    "Conditioning": {
        "color": "#3f7a3f",
        "order": 1,
    },
    "ControlNet": {
        "color": "#2d6b6b",
        "order": 2,
    },
    "Sampler": {
        "color": "#6b3fa0",
        "order": 3,
    },
    "Latent": {
        "color": "#7a6b3f",
        "order": 4,
    },
    "Image": {
        "color": "#a0522d",
        "order": 5,
    },
    "Utility": {
        "color": "#555555",
        "order": 6,
    },
    "Output": {
        "color": "#8b1a1a",   # deep red - results/save nodes
        "order": 99,           # rightmost column
    },
}

# Group title labels shown in ComfyUI canvas
CONSOLE_GROUP_LABELS = {
    "Input":  "📥 Input Console",
    "Output": "📤 Output Console",
}

# Layout geometry constants
NODE_WIDTH = 240
NODE_HEIGHT_BASE = 120
NODE_HEIGHT_PER_WIDGET = 28
COLUMN_GAP = 120        # must be > GROUP_PADDING*2 to prevent group overlap
ROW_GAP = 60
GROUP_PADDING = 50      # padding inside group bounding box
CANVAS_START_X = 200
CANVAS_START_Y = 400    # leave room above for header note
