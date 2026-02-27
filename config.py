"""
config.py — Configuración central del Podcast Clip Tool
Maneja secrets (Streamlit Cloud / .env local) y constantes globales.
"""

import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def get_secret(key: str) -> str:
    """
    Obtiene un secret: primero busca en st.secrets (Streamlit Cloud),
    luego en variables de entorno (local con .env).
    Lanza ValueError si no se encuentra.
    """
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        pass

    value = os.environ.get(key)
    if not value:
        raise ValueError(
            f"Secret '{key}' no encontrado. "
            f"Configúralo en Streamlit Cloud (Settings → Secrets) "
            f"o en tu archivo .env."
        )
    return value


# ── Modelos ──────────────────────────────────────────────────────────────────
WHISPER_MODEL = "whisper-1"
CLAUDE_MODEL = "claude-sonnet-4-6"
WHISPER_LANGUAGE = "es"

# ── Subtítulos estilo TikTok ─────────────────────────────────────────────────
SUBTITLE_FONT_SIZE = 88          # pt — grande y legible en mobile
SUBTITLE_FONT_COLOR = "&H00FFFFFF"       # Blanco (ASS: AABBGGRR) — palabras futuras
SUBTITLE_SECONDARY_COLOR = "&H0000FFFF" # Amarillo — relleno karaoke \kf
SUBTITLE_OUTLINE_COLOR = "&H00000000"   # Negro
SUBTITLE_OUTLINE_WIDTH = 4       # px
SUBTITLE_BOLD = 1
SUBTITLE_ALIGNMENT = 2           # 2 = center-bottom (estándar ASS)
SUBTITLE_MARGIN_V = 80           # margen vertical desde el borde inferior
SUBTITLE_WORDS_PER_LINE = 5      # palabras por línea en el karaoke

# ── Video ────────────────────────────────────────────────────────────────────
TARGET_ASPECT = "9:16"
TARGET_WIDTH = 1080              # resolución objetivo (TikTok estándar)
TARGET_HEIGHT = 1920
HORIZONTAL_CROP_FILTER = "crop=ih*9/16:ih:(iw-ih*9/16)/2:0"
VIDEO_CODEC = "libx264"
AUDIO_CODEC = "aac"
VIDEO_CRF = 18                   # calidad de compresión (menor = mejor calidad)
VIDEO_PRESET = "fast"            # velocidad de encoding en Streamlit Cloud

# ── Audio para Whisper ───────────────────────────────────────────────────────
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_BITRATE = "32k"
AUDIO_FORMAT = "mp3"

# ── Naming de archivos ───────────────────────────────────────────────────────
PODCAST_NAME = "ladrando-ideas"
OUTPUT_VIDEO_EXT = ".mp4"
OUTPUT_AUDIO_EXT = ".mp3"
OUTPUT_SUBTITLE_EXT = ".srt"

# ── UI ───────────────────────────────────────────────────────────────────────
APP_TITLE = "🎙️ Podcast Clip Tool — Ladrando Ideas"
MAX_UPLOAD_MB = 500
DEFAULT_MIN_DURATION = 30        # segundos
DEFAULT_MAX_DURATION = 90        # segundos
MAX_VIRAL_MOMENTS = 3
