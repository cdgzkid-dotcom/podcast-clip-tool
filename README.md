# 🎙️ Podcast Clip Tool — Ladrando Ideas

Genera clips virales para TikTok e Instagram a partir de episodios del podcast **Ladrando Ideas**.

## Funcionalidades

- **Modo Manual**: corta un clip con timestamps exactos (HH:MM:SS)
- **Modo Automático**: Claude detecta los 3 mejores momentos virales del episodio
- Detecta orientación del video: iPhone (vertical) y Zoom (horizontal → center crop a 9:16)
- Subtítulos karaoke palabra por palabra quemados en el video
- Captions optimizados para TikTok e Instagram generados con IA
- Transcripción en español con Whisper API
- Descarga: MP4 + SRT por clip

## Stack

| Componente | Tecnología |
|---|---|
| UI | Streamlit |
| Transcripción | OpenAI Whisper API (`whisper-1`) |
| IA viral / captions | Anthropic Claude (`claude-sonnet-4-6`) |
| Video processing | ffmpeg |
| Deploy | Streamlit Cloud |

## Deploy en Streamlit Cloud

### 1. Preparar el repositorio

```bash
cd /Users/christian/podcast-clip-tool
git init
git add .
git commit -m "feat: initial Podcast Clip Tool — Ladrando Ideas"
```

### 2. Crear repositorio en GitHub

Ve a [github.com/new](https://github.com/new), crea un repo llamado `podcast-clip-tool` y luego:

```bash
git remote add origin https://github.com/TU_USUARIO/podcast-clip-tool.git
git branch -M main
git push -u origin main
```

### 3. Configurar Streamlit Cloud

1. Ve a [share.streamlit.io](https://share.streamlit.io) → **New app**
2. Selecciona el repositorio `podcast-clip-tool`
3. Archivo principal: `app.py`
4. En **Settings → Secrets**, añade:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
OPENAI_API_KEY = "sk-..."
```

5. Haz clic en **Deploy**

### 4. Monitorear el deploy

Streamlit Cloud instalará automáticamente:
- Python packages desde `requirements.txt`
- `ffmpeg` desde `packages.txt`

El primer deploy tarda ~2–3 minutos. Revisa los logs si hay errores.

## Desarrollo local (opcional)

```bash
cd podcast-clip-tool
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Instalar ffmpeg: brew install ffmpeg  (macOS)

# Crear .env con tus keys:
cp .env.example .env
# Editar .env y agregar las keys

streamlit run app.py
```

## Estructura

```
podcast-clip-tool/
├── app.py           — UI Streamlit
├── cutter.py        — ffmpeg: corte + crop + orientación
├── transcriber.py   — Whisper API + extracción de audio
├── subtitles.py     — Subtítulos ASS karaoke + SRT + quemado
├── ai_agent.py      — Claude: detección viral + captions
├── exporter.py      — Packaging para descarga
├── config.py        — Configuración central + secrets
├── requirements.txt
├── packages.txt     — ffmpeg (Streamlit Cloud)
└── .streamlit/
    └── config.toml  — maxUploadSize=500, tema oscuro
```

## Variables de entorno

| Variable | Descripción |
|---|---|
| `ANTHROPIC_API_KEY` | API key de Anthropic (Claude) |
| `OPENAI_API_KEY` | API key de OpenAI (Whisper) |

En Streamlit Cloud: Settings → Secrets
En local: archivo `.env` en la raíz del proyecto
