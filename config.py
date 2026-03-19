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

# ── Podcasts ──────────────────────────────────────────────────────────────────
PODCASTS = {
    "ladrando-ideas": {
        "display_name": "Ladrando Ideas",
        "slug": "ladrando-ideas",
    },
    "ftbp": {
        "display_name": "Fuck The Business Plan",
        "slug": "ftbp",
    },
}
PODCAST_DISPLAY_NAMES = [p["display_name"] for p in PODCASTS.values()]

# ── Clips ─────────────────────────────────────────────────────────────────────
CLIP_DURATION_SECONDS = 60       # duración objetivo de cada clip (exacta)
CLIP_DURATION_TOLERANCE = 5      # ±segundos aceptables por corte natural
MAX_VIRAL_MOMENTS = 3

# ── Subtítulos estilo Instagram Reels ────────────────────────────────────────
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
TARGET_WIDTH = 1080              # resolución Instagram Reels estándar
TARGET_HEIGHT = 1920
VIDEO_CODEC = "libx264"
AUDIO_CODEC = "aac"
VIDEO_CRF = 18                   # calidad de compresión (menor = mejor calidad)
VIDEO_PRESET = "fast"            # velocidad de encoding en Streamlit Cloud

# ── Normalización de audio ───────────────────────────────────────────────────
# dynaudnorm: iguala volúmenes entre locutor callado y locutor normal (por frame)
#   f=300  → ventana de 300ms para detectar cambios de volumen (suaviza sin cortar sílabas)
#   g=5    → suavizado gaussiano — evita saltos bruscos de ganancia
#   m=10   → ganancia mínima ×10 (evita amplificar el silencio de fondo)
# loudnorm: lleva el nivel final a estándar de redes sociales (-16 LUFS)
AUDIO_NORMALIZE_FILTER = "dynaudnorm=f=300:g=5:m=10,loudnorm=I=-16:TP=-1.5:LRA=11"

# ── Audio para Whisper ───────────────────────────────────────────────────────
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_BITRATE = "32k"
AUDIO_FORMAT = "mp3"
SUPPORTED_AUDIO_FORMATS = ["mp3", "m4a", "wav", "MP3", "M4A", "WAV"]

# ── Naming de archivos ───────────────────────────────────────────────────────
OUTPUT_VIDEO_EXT = ".mp4"
OUTPUT_AUDIO_EXT = ".mp3"
OUTPUT_SUBTITLE_EXT = ".srt"

# ── UI ───────────────────────────────────────────────────────────────────────
APP_TITLE = "🎙️ Podcast Clip Tool"
MAX_UPLOAD_MB = 500
