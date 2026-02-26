"""
cutter.py — Corte y procesamiento de video con ffmpeg.

Responsabilidades:
- Detectar orientación del video (vertical 9:16 vs horizontal 16:9)
- Cortar clip por timestamps
- Aplicar center crop de 16:9 a 9:16 para videos de Zoom
"""

import json
import os
import subprocess
import tempfile

from config import (
    AUDIO_CODEC,
    HORIZONTAL_CROP_FILTER,
    VIDEO_CODEC,
    VIDEO_CRF,
    VIDEO_PRESET,
)


def detect_orientation(filepath: str) -> str:
    """
    Detecta la orientación del video usando ffprobe.

    Returns:
        "vertical"   si height > width  (iPhone, ya listo para TikTok)
        "horizontal" si width >= height (Zoom, necesita center crop)
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        filepath,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)

    # Buscar el stream de video
    width, height = None, None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            width = int(stream.get("width", 0))
            height = int(stream.get("height", 0))
            # Considerar rotación (ej: iPhone puede reportar 1920x1080 con rotate=90)
            rotation = 0
            tags = stream.get("tags", {})
            if "rotate" in tags:
                rotation = abs(int(tags["rotate"]))
            # Con side_data también puede venir la rotación
            for sd in stream.get("side_data_list", []):
                if sd.get("side_data_type") == "Display Matrix":
                    rotation = abs(int(sd.get("rotation", 0)))
            # Si hay rotación de 90 o 270 grados, intercambiar ancho/alto
            if rotation in (90, 270):
                width, height = height, width
            break

    if width is None or height is None:
        raise ValueError(f"No se pudo determinar las dimensiones de: {filepath}")

    return "vertical" if height > width else "horizontal"


def cut_clip(input_path: str, start_time: str, end_time: str, output_path: str) -> str:
    """
    Corta un clip del video entre start_time y end_time.

    Args:
        input_path:  ruta al video original
        start_time:  tiempo de inicio en formato HH:MM:SS o segundos
        end_time:    tiempo de fin en formato HH:MM:SS o segundos
        output_path: ruta de destino del clip

    Returns:
        output_path si éxito
    """
    cmd = [
        "ffmpeg",
        "-y",                    # sobreescribir si existe
        "-ss", str(start_time),  # seek input (más rápido antes de -i)
        "-to", str(end_time),
        "-i", input_path,
        "-c:v", VIDEO_CODEC,
        "-crf", str(VIDEO_CRF),
        "-preset", VIDEO_PRESET,
        "-c:a", AUDIO_CODEC,
        "-avoid_negative_ts", "make_zero",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg falló al cortar el clip.\n"
            f"Comando: {' '.join(cmd)}\n"
            f"Error: {result.stderr}"
        )
    return output_path


def crop_to_vertical(input_path: str, output_path: str) -> str:
    """
    Aplica center crop de 16:9 a 9:16.
    Fórmula: crop=ih*9/16:ih:(iw-ih*9/16)/2:0

    Args:
        input_path:  video horizontal (16:9)
        output_path: video vertical (9:16) resultante

    Returns:
        output_path si éxito
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-vf", HORIZONTAL_CROP_FILTER,
        "-c:v", VIDEO_CODEC,
        "-crf", str(VIDEO_CRF),
        "-preset", VIDEO_PRESET,
        "-c:a", AUDIO_CODEC,
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg falló al hacer crop.\n"
            f"Error: {result.stderr}"
        )
    return output_path


def process_video(
    input_path: str,
    start_time: str,
    end_time: str,
    output_path: str,
) -> str:
    """
    Pipeline completo: corta el clip y aplica crop si es horizontal.

    Flujo:
        1. Cortar clip → archivo temporal
        2. Detectar orientación del clip cortado
        3. Si horizontal → center crop → output_path
        4. Si vertical → mover a output_path directamente

    Args:
        input_path:  video original (MOV o MP4)
        start_time:  "HH:MM:SS" o segundos flotantes
        end_time:    "HH:MM:SS" o segundos flotantes
        output_path: destino final del clip procesado

    Returns:
        output_path
    """
    # Crear archivo temporal para el clip sin crop
    suffix = os.path.splitext(input_path)[1] or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_cut_path = tmp.name

    try:
        # Paso 1: cortar
        cut_clip(input_path, start_time, end_time, tmp_cut_path)

        # Paso 2: detectar orientación del clip ya cortado
        orientation = detect_orientation(tmp_cut_path)

        # Paso 3: crop si es necesario
        if orientation == "horizontal":
            crop_to_vertical(tmp_cut_path, output_path)
        else:
            # Vertical: solo re-encodar para garantizar formato limpio
            cmd = [
                "ffmpeg", "-y",
                "-i", tmp_cut_path,
                "-c:v", VIDEO_CODEC,
                "-crf", str(VIDEO_CRF),
                "-preset", VIDEO_PRESET,
                "-c:a", AUDIO_CODEC,
                output_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg falló al re-encodar: {result.stderr}")

    finally:
        # Limpiar temporal
        if os.path.exists(tmp_cut_path):
            os.unlink(tmp_cut_path)

    return output_path
