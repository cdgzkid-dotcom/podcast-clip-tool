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
        "hosts": "Christian + Kiko",
    },
    "ftbp": {
        "display_name": "Fuck The Business Plan",
        "slug": "ftbp",
        "hosts": "Christian Dominguez + JC Rico",
    },
}
PODCAST_DISPLAY_NAMES = [p["display_name"] for p in PODCASTS.values()]

# ── Clips ─────────────────────────────────────────────────────────────────────
CLIP_DURATION_SECONDS = 60       # duración objetivo de cada clip (exacta)
CLIP_DURATION_TOLERANCE = 5      # ±segundos aceptables por corte natural
MAX_VIRAL_MOMENTS = 3

# ── Subtítulos estilo Instagram Reels ────────────────────────────────────────
SUBTITLE_FONT_NAME = "Roboto"    # Google Fonts — instalado via packages.txt
SUBTITLE_FONTS_DIR = "/usr/share/fonts/truetype/roboto"  # ruta Debian post-install
SUBTITLE_FONT_SIZE = 96          # pt — grande y legible en mobile
SUBTITLE_FONT_COLOR = "&H00FFFFFF"     # Blanco (ASS: AABBGGRR)
SUBTITLE_OUTLINE_COLOR = "&H00000000" # Negro
SUBTITLE_OUTLINE_WIDTH = 0       # sin outline — texto blanco limpio
SUBTITLE_BOLD = 1
SUBTITLE_ALIGNMENT = 2           # 2 = center-bottom (estándar ASS)
SUBTITLE_MARGIN_V = 480          # px desde borde inferior — encima de la barra negra
SUBTITLE_WORDS_PER_LINE = 7      # palabras por línea — acumula como CapCut

# ── Video ────────────────────────────────────────────────────────────────────
TARGET_ASPECT = "9:16"
TARGET_WIDTH = 1080              # resolución Instagram Reels estándar
TARGET_HEIGHT = 1920
LINKEDIN_WIDTH = 1080            # cuadrado para LinkedIn
LINKEDIN_HEIGHT = 1080
SUBTITLE_LINKEDIN_FONT_SIZE = 72
SUBTITLE_LINKEDIN_MARGIN_V = 120
VIDEO_CODEC = "libx264"
AUDIO_CODEC = "aac"
VIDEO_CRF = 18                   # calidad de compresión (menor = mejor calidad)
VIDEO_PRESET = "ultrafast"       # velocidad de encoding — sin diferencia visual en imagen estática

# ── Normalización de audio ───────────────────────────────────────────────────
# speechnorm: detecta segmentos de habla y solo normaliza esos, dejando la
#   música e intros relativamente sin tocar (diseñado para podcasts).
#   p=0.95 → pico objetivo (95% del máximo)
#   e=30   → qué tan agresivo es el boost en habla callada
#   r=0.0001 → umbral para distinguir habla de silencio/música
# loudnorm: lleva el nivel final a estándar de redes sociales (-16 LUFS)
AUDIO_NORMALIZE_FILTER = "speechnorm=p=0.95:e=30:r=0.0001,loudnorm=I=-16:TP=-1.5:LRA=11"

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
