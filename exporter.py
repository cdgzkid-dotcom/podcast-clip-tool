"""
exporter.py — Packaging de clips para descarga.

Responsabilidades:
- Construir nombres de archivos consistentes
- Leer archivos generados en memoria para st.download_button
- Empaquetar todos los outputs de un clip en un dict listo para la UI
"""

import os

from config import PODCAST_NAME


def build_filename(clip_index: int, episode_number: int) -> str:
    """
    Construye el nombre base del clip (sin extensión).

    Ejemplo: clip_01_ladrando-ideas_ep05

    Args:
        clip_index:     índice del clip (1-based)
        episode_number: número del episodio

    Returns:
        Nombre base sin extensión
    """
    return f"clip_{clip_index:02d}_{PODCAST_NAME}_ep{episode_number:02d}"


def package_clip_output(
    clip_index: int,
    episode_number: int,
    video_path: str,
    srt_path: str,
    transcript_text: str,
    tiktok_caption: str,
    instagram_caption: str,
) -> dict:
    """
    Lee los archivos generados en memoria y empaqueta todo para la UI.

    Los bytes se leen en memoria para que Streamlit pueda ofrecerlos
    como descarga sin depender de que los archivos temporales sigan
    existiendo cuando el usuario haga clic en el botón de descarga.

    Args:
        clip_index:        índice del clip (1-based)
        episode_number:    número del episodio
        video_path:        ruta al video MP4 con subtítulos quemados
        srt_path:          ruta al archivo SRT
        transcript_text:   texto plano del transcript del clip
        tiktok_caption:    caption generado para TikTok
        instagram_caption: caption generado para Instagram

    Returns:
        Dict con:
        {
            "filename_base":     str   — ej. "clip_01_ladrando-ideas_ep05",
            "video_bytes":       bytes — video listo para st.download_button,
            "srt_bytes":         bytes — SRT listo para st.download_button,
            "transcript":        str   — texto del transcript,
            "tiktok_caption":    str   — caption TikTok,
            "instagram_caption": str   — caption Instagram,
        }

    Raises:
        FileNotFoundError: si video_path o srt_path no existen
    """
    filename_base = build_filename(clip_index, episode_number)

    with open(video_path, "rb") as f:
        video_bytes = f.read()

    with open(srt_path, "rb") as f:
        srt_bytes = f.read()

    return {
        "filename_base":     filename_base,
        "video_bytes":       video_bytes,
        "srt_bytes":         srt_bytes,
        "transcript":        transcript_text,
        "tiktok_caption":    tiktok_caption,
        "instagram_caption": instagram_caption,
    }
