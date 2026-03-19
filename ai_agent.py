"""
ai_agent.py — Integración con Claude API.

Responsabilidades:
- Detectar los 3 mejores momentos virales en el transcript (modo automático)
- Generar captions optimizados para TikTok e Instagram en español
"""

import json
import re

import anthropic

from config import CLAUDE_MODEL, CLIP_DURATION_SECONDS, CLIP_DURATION_TOLERANCE, get_secret

# ── Prompts ───────────────────────────────────────────────────────────────────

_VIRAL_SYSTEM_PROMPT = """Eres un experto en contenido viral para redes sociales,
especializado en podcasts en español latinoamericano. Tu tarea es identificar
los momentos más poderosos de un transcript de podcast que funcionarían como
clips de Instagram Reels.

Un buen momento viral tiene:
- Un hook fuerte en los primeros 3 segundos (pregunta, afirmación sorprendente,
  contradicción, o historia)
- Una idea completa y comprensible sin contexto externo
- Valor emocional o informativo claro (humor, aprendizaje, inspiración, sorpresa)
- Inicio exacto al comienzo de una oración o idea — NUNCA a mitad de frase
- Fin exacto al terminar una oración o idea — NUNCA cortando una palabra o frase

Responde ÚNICAMENTE con JSON válido, sin markdown, sin explicaciones, sin texto
adicional antes o después del JSON."""

_VIRAL_USER_TEMPLATE = """Analiza este transcript del episodio {episode_number} del
podcast "{podcast_name}" y encuentra los 3 mejores momentos para clips de Instagram Reels.

RESTRICCIONES — LEE CON ATENCIÓN:
- La duración de cada clip DEBE ser entre {min_duration}s y {max_duration}s. NI UN SEGUNDO MÁS.
- Antes de escribir el JSON, calcula: end_time - start_time. Si el resultado supera {max_duration},
  ajusta el end_time para que la diferencia sea exactamente {target_duration}s.
- Los timestamps son en segundos decimales (no MM:SS). Convierte los [MM:SS] del transcript
  multiplicando minutos × 60 y sumando segundos.
- El inicio DEBE coincidir con el comienzo de una oración completa.
- El fin DEBE coincidir con el final de una oración completa.
- Los momentos pueden venir de CUALQUIER parte del episodio, no solo del inicio.
- Busca en todo el transcript y elige los más virales, aunque estén al final.

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
Creas captions que maximizan el engagement y el crecimiento orgánico en Instagram."""

_CAPTION_INSTAGRAM_TEMPLATE = """Crea un caption para Instagram Reels para este clip del
podcast "{podcast_name}" — Temporada {season_number}, Episodio {episode_number}.

TRANSCRIPT DEL CLIP:
{clip_transcript}

REQUISITOS DEL CAPTION:
- Primera línea: hook fuerte (máximo 125 caracteres, se muestra antes del "más")
- Cuerpo: 2-4 oraciones que expanden la idea del clip
- Incluye la reflexión o aprendizaje clave
- Call-to-action: pregunta que invite a comentar o guardar
- Menciona la temporada y episodio de forma natural en el cuerpo (ej: "en el ep. {episode_number} de la temp. {season_number}")
- Hashtags: 8-12 hashtags, mezcla de nicho + generales en español e inglés
- Separa el cuerpo de los hashtags con una línea en blanco
- Tono reflexivo pero accesible, conversacional

Responde solo con el caption, sin comillas, sin explicaciones."""


# ── Funciones principales ──────────────────────────────────────────────────────

def detect_viral_moments(
    transcript_text: str,
    episode_number: int,
    podcast_name: str,
) -> list[dict]:
    """
    Usa Claude para detectar los 3 mejores momentos virales del transcript.

    Duración objetivo: CLIP_DURATION_SECONDS (60s) ± CLIP_DURATION_TOLERANCE (5s).
    Los timestamps retornados se snapean después a límites de palabras en app.py.

    Args:
        transcript_text: transcript formateado con timestamps ([MM:SS] texto)
        episode_number:  número del episodio
        podcast_name:    nombre del podcast para el prompt

    Returns:
        Lista de hasta 3 dicts con keys:
        {start_time, end_time, duration_seconds, reason, viral_score, hook}

    Raises:
        ValueError: si la respuesta de Claude no es JSON válido
        RuntimeError: si hay error en la API
    """
    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

    target = CLIP_DURATION_SECONDS
    tolerance = CLIP_DURATION_TOLERANCE

    user_message = _VIRAL_USER_TEMPLATE.format(
        episode_number=episode_number,
        podcast_name=podcast_name,
        target_duration=target,
        min_duration=target - tolerance,
        max_duration=target + tolerance,
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


def generate_instagram_caption(
    clip_transcript: str,
    season_number: int,
    episode_number: int,
    podcast_name: str,
) -> str:
    """
    Genera un caption optimizado para Instagram Reels.

    Args:
        clip_transcript: texto del transcript del clip
        episode_number:  número del episodio
        podcast_name:    nombre del podcast

    Returns:
        Caption como string listo para copiar/pegar
    """
    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

    user_message = _CAPTION_INSTAGRAM_TEMPLATE.format(
        season_number=season_number,
        episode_number=episode_number,
        podcast_name=podcast_name,
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


def generate_episode_description(
    transcript_text: str,
    episode_title: str,
    podcast_name: str,
    season_number: int,
    episode_number: int,
) -> dict:
    """
    Genera título final y descripción para Spotify a partir del transcript completo.

    Returns:
        {"title": str, "description": str}
    """
    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

    prompt = f"""Eres el productor del podcast "{podcast_name}".
Leíste la transcripción completa del episodio y ahora tienes que escribir
el título y la descripción que aparecerá en Spotify.

TÍTULO PROPUESTO POR EL HOST: {episode_title}
TEMPORADA: {season_number} | EPISODIO: {episode_number}

REQUISITOS DEL TÍTULO:
- Si el propuesto ya es bueno, úsalo tal cual o mejóralo mínimamente
- Que sea directo y represente lo que realmente se habló

REQUISITOS DE LA DESCRIPCIÓN:
- Entre 120 y 200 palabras — suficiente para que el oyente sepa qué va a escuchar
- Menciona de 4 a 6 temas o momentos específicos que SÍ ocurrieron en el episodio
  (usa el transcript, no inventes nada)
- Tono conversacional, como hablan los hosts, no corporativo ni dramático
- Sin frases de hype: nada de "¡No te lo pierdas!", "Imprescindible", "Épico", etc.
- Puedes estructurarlo en 2 párrafos cortos si ayuda a la lectura
- Termina mencionando dónde escucharlo o con una invitación natural, no cursi

TRANSCRIPT COMPLETO DEL EPISODIO:
{transcript_text[:120000]}

Responde ÚNICAMENTE con JSON válido, sin markdown:
{{
  "title": "Título del episodio",
  "description": "Descripción para Spotify..."
}}"""

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as e:
        raise RuntimeError(f"Error al llamar a la Claude API: {e}") from e

    raw = _extract_json_block(response.content[0].text.strip())
    try:
        data = json.loads(raw)
        return {"title": data.get("title", ""), "description": data.get("description", "")}
    except json.JSONDecodeError:
        return {"title": episode_title, "description": response.content[0].text.strip()}


_LINKEDIN_CLIP_SYSTEM = """Eres el ghostwriter de un podcast de negocios en español.
Escribes posts de LinkedIn cortos y directos basados en un clip de podcast.

Voz: reflexiva, con experiencia real, párrafos cortos. Sin clichés motivacionales,
sin frases vacías. El tono es el de un profesional que comparte aprendizajes reales."""

_LINKEDIN_CLIP_TEMPLATE = """Escribe un post de LinkedIn para acompañar este clip del
podcast "{podcast_name}" — Temporada {season_number}, Episodio {episode_number}.

TRANSCRIPT DEL CLIP:
{clip_transcript}

ESTRUCTURA:
1. Una frase-gancho fuerte (cita o idea del clip, máximo 2 líneas)
2. Contexto o reflexión en 2-3 oraciones
3. El aprendizaje o insight clave del clip
4. Una pregunta corta de cierre para generar comentarios

RESTRICCIONES:
- Máximo 900 caracteres en total
- Sin hashtags
- Sin emojis (o máximo 1)
- Todo en español
- Tono profesional pero humano

Responde solo con el texto del post, sin comillas, sin explicaciones."""


def generate_linkedin_clip_copy(
    clip_transcript: str,
    season_number: int,
    episode_number: int,
    podcast_name: str,
) -> str:
    """
    Genera copy de LinkedIn para un clip específico (no el episodio completo).

    Args:
        clip_transcript: texto del clip
        season_number:   número de temporada
        episode_number:  número de episodio
        podcast_name:    nombre del podcast

    Returns:
        Copy como string listo para copiar/pegar en LinkedIn
    """
    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

    user_message = _LINKEDIN_CLIP_TEMPLATE.format(
        podcast_name=podcast_name,
        season_number=season_number,
        episode_number=episode_number,
        clip_transcript=clip_transcript,
    )

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            system=_LINKEDIN_CLIP_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIError as e:
        raise RuntimeError(f"Error al llamar a la Claude API: {e}") from e

    return response.content[0].text.strip()


def generate_linkedin_image(image_prompt: str) -> bytes:
    """
    Genera una imagen para el post de LinkedIn usando DALL-E 3.

    Args:
        image_prompt: descripción en inglés generada por Claude

    Returns:
        bytes de la imagen PNG/JPEG lista para descargar
    """
    client = openai.OpenAI(api_key=get_secret("OPENAI_API_KEY"))

    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=image_prompt,
            size="1792x1024",
            quality="standard",
            n=1,
        )
    except openai.OpenAIError as e:
        raise RuntimeError(f"Error al generar imagen con DALL-E 3: {e}") from e

    image_url = response.data[0].url
    with urllib.request.urlopen(image_url) as r:
        return r.read()


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
