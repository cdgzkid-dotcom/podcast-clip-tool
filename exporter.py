"""
exporter.py — Packaging de clips para descarga.

Responsabilidades:
- Construir nombres de archivos consistentes
- Leer archivos generados en memoria para st.download_button
- Empaquetar todos los outputs de un clip en un dict listo para la UI
"""

import os

def build_filename(clip_index: int, episode_number: int, podcast_slug: str) -> str:
    """
    Construye el nombre base del clip (sin extensión).

    Ejemplo: clip_01_ladrando-ideas_ep05
             clip_01_ftbp_ep03

    Args:
        clip_index:     índice del clip (1-based)
        episode_number: número del episodio
        podcast_slug:   slug del podcast ("ladrando-ideas" | "ftbp")

    Returns:
        Nombre base sin extensión
    """
    return f"clip_{clip_index:02d}_{podcast_slug}_ep{episode_number:02d}"


def package_clip_output(
    clip_index: int,
    episode_number: int,
    podcast_slug: str,
    video_path: str,
    srt_path: str,
    transcript_text: str,
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
        podcast_slug:      slug del podcast ("ladrando-ideas" | "ftbp")
        video_path:        ruta al video MP4 con subtítulos quemados
        srt_path:          ruta al archivo SRT
        transcript_text:   texto plano del transcript del clip
        instagram_caption: caption generado para Instagram

    Returns:
        Dict con:
        {
            "filename_base":     str   — ej. "clip_01_ladrando-ideas_ep05",
            "video_bytes":       bytes — video listo para st.download_button,
            "srt_bytes":         bytes — SRT listo para st.download_button,
            "transcript":        str   — texto del transcript,
            "instagram_caption": str   — caption Instagram,
        }

    Raises:
        FileNotFoundError: si video_path o srt_path no existen
    """
    filename_base = build_filename(clip_index, episode_number, podcast_slug)

    with open(video_path, "rb") as f:
        video_bytes = f.read()

    with open(srt_path, "rb") as f:
        srt_bytes = f.read()

    return {
        "filename_base":     filename_base,
        "video_bytes":       video_bytes,
        "srt_bytes":         srt_bytes,
        "transcript":        transcript_text,
        "instagram_caption": instagram_caption,
    }
