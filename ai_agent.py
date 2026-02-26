"""
ai_agent.py — Integración con Claude API.

Responsabilidades:
- Detectar los 3 mejores momentos virales en el transcript (modo automático)
- Generar captions optimizados para TikTok e Instagram en español
"""

import json
import re

import anthropic

from config import CLAUDE_MODEL, PODCAST_NAME, get_secret

# ── Prompts ───────────────────────────────────────────────────────────────────

_VIRAL_SYSTEM_PROMPT = """Eres un experto en contenido viral para redes sociales,
especializado en podcasts en español latinoamericano. Tu tarea es identificar
los momentos más poderosos de un transcript de podcast que funcionarían como
clips standalone en TikTok e Instagram Reels.

Un buen momento viral tiene:
- Un hook fuerte en los primeros 3 segundos (pregunta, afirmación sorprendente,
  contradicción, o historia)
- Una idea completa y comprensible sin contexto externo
- Valor emocional o informativo claro (humor, aprendizaje, inspiración, sorpresa)
- Inicio y fin naturales (no cortado en medio de una oración)

Responde ÚNICAMENTE con JSON válido, sin markdown, sin explicaciones, sin texto
adicional antes o después del JSON."""

_VIRAL_USER_TEMPLATE = """Analiza este transcript del episodio {episode_number} del
podcast "{podcast_name}" y encuentra los 3 mejores momentos para clips virales.

RESTRICCIONES IMPORTANTES:
- Cada clip debe durar entre {min_duration} y {max_duration} segundos
- Los timestamps son en segundos desde el inicio del video
- Los momentos deben ser autocontenidos (comprensibles sin contexto extra)
- El inicio del clip debe coincidir con el inicio de una oración o idea
- El fin del clip debe coincidir con el final de una oración o idea

TRANSCRIPT (formato [MM:SS] texto):
{transcript}

Responde con este JSON exacto (sin markdown):
{{
  "moments": [
    {{
      "start_time": 0.0,
      "end_time": 0.0,
      "duration_seconds": 0,
      "reason": "Por qué este momento es viral",
      "viral_score": 8,
      "hook": "Las primeras palabras del clip (el hook)"
    }}
  ]
}}"""

_CAPTION_SYSTEM_PROMPT = """Eres un experto en copywriting para redes sociales,
especializado en contenido de podcasts en español latinoamericano.
Creas captions que maximizan el engagement y el crecimiento orgánico."""

_CAPTION_TIKTOK_TEMPLATE = """Crea un caption para TikTok para este clip del
episodio {episode_number} del podcast "{podcast_name}".

TRANSCRIPT DEL CLIP:
{clip_transcript}

REQUISITOS DEL CAPTION:
- Máximo 150 caracteres para el texto principal (TikTok trunca)
- Empieza con un hook que genere curiosidad o FOMO
- Usa 1 pregunta retórica si aplica
- Incluye un call-to-action sutil (ej: "¿Te pasó algo así?", "Comenta tu opinión")
- Termina con 3-5 hashtags relevantes en español + algunos en inglés para alcance
- Tono conversacional, cercano, no formal
- El caption debe funcionar como un teaser que complemente el video

Responde solo con el caption, sin comillas, sin explicaciones."""

_CAPTION_INSTAGRAM_TEMPLATE = """Crea un caption para Instagram para este clip del
episodio {episode_number} del podcast "{podcast_name}".

TRANSCRIPT DEL CLIP:
{clip_transcript}

REQUISITOS DEL CAPTION:
- Primera línea: hook fuerte (máximo 125 caracteres, se muestra antes del "más")
- Cuerpo: 2-4 oraciones que expanden la idea del clip
- Incluye la reflexión o aprendizaje clave
- Call-to-action: pregunta que invite a comentar o guardar
- Hashtags: 8-12 hashtags, mezcla de nicho + generales en español e inglés
- Separa el cuerpo de los hashtags con una línea en blanco
- Tono reflexivo pero accesible

Responde solo con el caption, sin comillas, sin explicaciones."""


# ── Funciones principales ──────────────────────────────────────────────────────

def detect_viral_moments(
    transcript_text: str,
    episode_number: int,
    min_duration: int = 30,
    max_duration: int = 90,
) -> list[dict]:
    """
    Usa Claude para detectar los 3 mejores momentos virales del transcript.

    Args:
        transcript_text: transcript formateado con timestamps ([MM:SS] texto)
        episode_number:  número del episodio
        min_duration:    duración mínima del clip en segundos
        max_duration:    duración máxima del clip en segundos

    Returns:
        Lista de hasta 3 dicts con keys:
        {start_time, end_time, duration_seconds, reason, viral_score, hook}

    Raises:
        ValueError: si la respuesta de Claude no es JSON válido
        RuntimeError: si hay error en la API
    """
    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

    user_message = _VIRAL_USER_TEMPLATE.format(
        episode_number=episode_number,
        podcast_name=PODCAST_NAME,
        min_duration=min_duration,
        max_duration=max_duration,
        transcript=transcript_text,
    )

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=_VIRAL_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIError as e:
        raise RuntimeError(f"Error al llamar a la Claude API: {e}") from e

    raw_text = response.content[0].text.strip()

    # Limpiar posibles bloques de markdown (```json ... ```)
    raw_text = _extract_json_block(raw_text)

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Claude retornó JSON inválido.\n"
            f"Respuesta cruda:\n{raw_text}\n"
            f"Error: {e}"
        ) from e

    moments = data.get("moments", [])

    # Validar y limpiar cada momento
    validated = []
    for m in moments:
        if not all(k in m for k in ("start_time", "end_time")):
            continue
        m["start_time"] = float(m["start_time"])
        m["end_time"] = float(m["end_time"])
        m["duration_seconds"] = int(m.get("duration_seconds", m["end_time"] - m["start_time"]))
        m["reason"] = m.get("reason", "Momento relevante")
        m["viral_score"] = int(m.get("viral_score", 7))
        m["hook"] = m.get("hook", "")
        validated.append(m)

    return validated[:3]  # máximo 3 momentos


def generate_caption(
    clip_transcript: str,
    episode_number: int,
    platform: str,
) -> str:
    """
    Genera un caption optimizado para TikTok o Instagram.

    Args:
        clip_transcript: texto del transcript del clip
        episode_number:  número del episodio
        platform:        "tiktok" | "instagram"

    Returns:
        Caption como string listo para copiar/pegar
    """
    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

    if platform == "tiktok":
        template = _CAPTION_TIKTOK_TEMPLATE
    else:
        template = _CAPTION_INSTAGRAM_TEMPLATE

    user_message = template.format(
        episode_number=episode_number,
        podcast_name=PODCAST_NAME,
        clip_transcript=clip_transcript,
    )

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            system=_CAPTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIError as e:
        raise RuntimeError(f"Error al llamar a la Claude API: {e}") from e

    return response.content[0].text.strip()


def generate_both_captions(
    clip_transcript: str,
    episode_number: int,
) -> dict:
    """
    Genera captions para TikTok e Instagram en una sola llamada.
    Retorna dict con keys "tiktok" y "instagram".
    """
    tiktok = generate_caption(clip_transcript, episode_number, "tiktok")
    instagram = generate_caption(clip_transcript, episode_number, "instagram")
    return {"tiktok": tiktok, "instagram": instagram}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_json_block(text: str) -> str:
    """
    Extrae el contenido JSON de un bloque markdown si existe.
    Soporta ```json ... ``` y ``` ... ```.
    Si no hay bloque, retorna el texto tal cual.
    """
    # Buscar bloque ```json ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        return match.group(1).strip()

    # Buscar el primer { y el último } para extraer el JSON directamente
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]

    return text
