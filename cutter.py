"""
cutter.py — Corte de audio y generación de video con ffmpeg.

Responsabilidades:
- Cortar segmento de audio por timestamps
- Crear video a partir de imagen de fondo + audio (para Instagram Reels)
"""

import os
import subprocess
import tempfile

from config import (
    AUDIO_CODEC,
    TARGET_HEIGHT,
    TARGET_WIDTH,
    VIDEO_CODEC,
    VIDEO_CRF,
    VIDEO_PRESET,
)


def cut_audio(input_path: str, start_sec: float, end_sec: float, output_path: str) -> str:
    """
    Corta un segmento de audio entre start_sec y end_sec.

    Args:
        input_path:  ruta al audio original (MP3, M4A, WAV)
        start_sec:   tiempo de inicio en segundos
        end_sec:     tiempo de fin en segundos
        output_path: ruta de destino del clip (MP3)

    Returns:
        output_path si éxito

    Raises:
        RuntimeError: si ffmpeg falla
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(start_sec),
        "-to", str(end_sec),
        "-i", input_path,
        "-c:a", AUDIO_CODEC,
        "-b:a", "192k",
        "-avoid_negative_ts", "make_zero",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg falló al cortar el audio.\n"
            f"Comando: {' '.join(cmd)}\n"
            f"Error: {result.stderr}"
        )
    return output_path


def create_video_from_audio(
    background_image_path: str,
    audio_path: str,
    output_path: str,
) -> str:
    """
    Crea un video de Instagram Reels (1080×1920) a partir de:
    - Una imagen de fondo estática (escalada/recortada para llenar el frame)
    - Un audio de clip (MP3/AAC)

    La imagen se escala para LLENAR completamente el frame 1080×1920
    (puede recortar ligeramente si el aspect ratio no es 9:16 exacto).

    Args:
        background_image_path: ruta a la imagen de fondo (JPG o PNG)
        audio_path:            ruta al audio del clip (MP3 o AAC)
        output_path:           ruta de destino del video MP4

    Returns:
        output_path si éxito

    Raises:
        RuntimeError: si ffmpeg falla
    """
    # Escalar para llenar 1080×1920 (crop si aspect ratio difiere)
    scale_filter = (
        f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:"
        f"force_original_aspect_ratio=increase,"
        f"crop={TARGET_WIDTH}:{TARGET_HEIGHT}"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-loop", "1",           # repetir imagen indefinidamente
        "-framerate", "1",      # 1 fps suficiente para imagen estática
        "-i", background_image_path,
        "-i", audio_path,
        "-vf", scale_filter,
        "-c:v", VIDEO_CODEC,
        "-tune", "stillimage",  # optimiza para imagen estática
        "-crf", str(VIDEO_CRF),
        "-preset", VIDEO_PRESET,
        "-c:a", AUDIO_CODEC,
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",  # compatibilidad máxima
        "-shortest",            # terminar cuando el audio termine
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg falló al crear el video.\n"
            f"Comando: {' '.join(cmd)}\n"
            f"Error: {result.stderr}"
        )
    return output_path


def process_clip(
    audio_input_path: str,
    start_sec: float,
    end_sec: float,
    background_image_path: str,
    output_video_path: str,
) -> str:
    """
    Pipeline completo para un clip:
    1. Cortar segmento de audio
    2. Crear video con imagen de fondo + audio cortado

    El quemado de subtítulos se hace DESPUÉS en app.py con burn_subtitles().

    Args:
        audio_input_path:      audio original del episodio
        start_sec:             inicio del clip en segundos
        end_sec:               fin del clip en segundos
        background_image_path: imagen de fondo para el video
        output_video_path:     destino del video sin subtítulos

    Returns:
        output_video_path
    """
    suffix = os.path.splitext(audio_input_path)[1] or ".mp3"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_audio_path = tmp.name

    try:
        cut_audio(audio_input_path, start_sec, end_sec, tmp_audio_path)
        create_video_from_audio(background_image_path, tmp_audio_path, output_video_path)
    finally:
        if os.path.exists(tmp_audio_path):
            os.unlink(tmp_audio_path)

    return output_video_path
