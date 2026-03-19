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
    AUDIO_NORMALIZE_FILTER,
    SUBTITLE_FONTS_DIR,
    TARGET_HEIGHT,
    TARGET_WIDTH,
    VIDEO_CODEC,
    VIDEO_CRF,
    VIDEO_PRESET,
)


def normalize_audio(input_path: str, output_path: str) -> str:
    """
    Normaliza el volumen del episodio completo antes de transcribir y cortar.

    dynaudnorm detecta frame a frame quién habla más callado y le sube la
    ganancia sin tocar al locutor que ya suena bien. loudnorm lleva el nivel
    final a -16 LUFS (estándar Instagram/podcasts).

    Args:
        input_path:  audio original del episodio (MP3, M4A, WAV)
        output_path: audio normalizado de destino (MP3)

    Returns:
        output_path si éxito

    Raises:
        RuntimeError: si ffmpeg falla
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-af", AUDIO_NORMALIZE_FILTER,
        "-codec:a", "libmp3lame",   # MP3 requiere libmp3lame, no aac
        "-b:a", "192k",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg falló al normalizar el audio.\n"
            f"Error: {result.stderr}"
        )
    return output_path


def cut_audio(input_path: str, start_sec: float, end_sec: float, output_path: str) -> str:
    """
    Corta un segmento de audio entre start_sec y end_sec.

    Args:
        input_path:  ruta al audio normalizado del episodio (MP3)
        start_sec:   tiempo de inicio en segundos
        end_sec:     tiempo de fin en segundos
        output_path: ruta de destino del clip (MP3)

    Returns:
        output_path si éxito

    Raises:
        RuntimeError: si ffmpeg falla
    """
    ext = os.path.splitext(output_path)[1].lower()
    if ext == ".wav":
        # PCM sin encoder delay — timing perfecto para sincronía de subtítulos
        codec_args = ["-c:a", "pcm_s16le"]
    else:
        codec_args = ["-c:a", "libmp3lame", "-b:a", "192k"]

    cmd = [
        "ffmpeg", "-y",
        "-accurate_seek",
        "-ss", str(start_sec),
        "-to", str(end_sec),
        "-i", input_path,
        *codec_args,
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
    ass_path: str = None,
) -> str:
    """
    Crea un video de Instagram Reels (1080×1920) quemando los subtítulos
    en la misma pasada de ffmpeg — una sola codificación, más rápido.

    Args:
        background_image_path: ruta a la imagen de fondo (JPG o PNG)
        audio_path:            ruta al audio del clip
        output_path:           ruta de destino del video MP4
        ass_path:              ruta al archivo .ass (opcional, quema subs en el mismo pass)
    """
    scale_filter = (
        f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:"
        f"force_original_aspect_ratio=decrease,"
        f"pad={TARGET_WIDTH}:{TARGET_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black"
    )

    if ass_path:
        import os as _os
        safe_ass = ass_path.replace("\\", "/").replace(":", "\\:")
        if _os.path.isdir(SUBTITLE_FONTS_DIR):
            safe_fonts = SUBTITLE_FONTS_DIR.replace(":", "\\:")
            vf = f"{scale_filter},ass={safe_ass}:fontsdir={safe_fonts}"
        else:
            vf = f"{scale_filter},ass={safe_ass}"
    else:
        vf = scale_filter

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-framerate", "1",
        "-i", background_image_path,
        "-i", audio_path,
        "-vf", vf,
        "-c:v", VIDEO_CODEC,
        "-tune", "stillimage",
        "-crf", str(VIDEO_CRF),
        "-preset", VIDEO_PRESET,
        "-c:a", AUDIO_CODEC,
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
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
    ass_path: str = None,
) -> str:
    """
    Pipeline completo para un clip en una sola pasada de ffmpeg:
    1. Corta audio a WAV (sin encoder delay → timing perfecto)
    2. Crea video + quema subtítulos en el mismo comando

    Args:
        audio_input_path:      audio original del episodio
        start_sec:             inicio del clip en segundos
        end_sec:               fin del clip en segundos
        background_image_path: imagen de fondo para el video
        output_video_path:     destino del video final
        ass_path:              archivo .ass para quemar subs (opcional)
    """
    # WAV: sin encoder delay, timing perfecto para sincronía de subtítulos
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_audio_path = tmp.name

    try:
        cut_audio(audio_input_path, start_sec, end_sec, tmp_audio_path)
        create_video_from_audio(background_image_path, tmp_audio_path, output_video_path, ass_path)
    finally:
        if os.path.exists(tmp_audio_path):
            os.unlink(tmp_audio_path)

    return output_video_path
