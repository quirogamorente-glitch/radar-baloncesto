# Radar de baloncesto

Radar automático de noticias de baloncesto para el feed **News by Óscar Q**, con especial atención al **UCAM Murcia CB** y al **Covirán Granada**.

## Qué hace

Cada 20 minutos, GitHub revisa las fuentes de [`fuentes.yml`](fuentes.yml) y guarda lo nuevo en [`noticias.json`](noticias.json), que el feed lee en cada actualización:

- Webs oficiales (Fundación CB Granada, UCAM Deportes).
- Medios especializados (Gigantes, Eurohoops, Solobasket).
- Búsquedas en Google Noticias: UCAM, Covirán, Liga Endesa, Euroliga, EuroCup, BCL, Primera FEB y los periodistas Olga Lorente, Jaime Nadal y Noelia Gómez Mira.

Cada noticia lleva **etiquetas** (`ucam`, `granada`, `periodista`, `acb`, `euroliga`, `eurocup`, `bcl`, `feb`, `posible_rumor`). Solo guarda las de las últimas 72 horas.

> ⚠️ El radar **avisa**, no verifica. El feed comprueba cada noticia en su fuente antes de publicarla, con sus reglas de siempre.

## Archivos

| Archivo | Para qué |
|---|---|
| `fuentes.yml` | Lista de fuentes y palabras clave. **Es el único que conviene tocar.** |
| `noticias.json` | Novedades detectadas (lo genera el radar). |
| `estado.json` | Qué fuentes funcionan y cuáles fallan. |
| `radar.py` | El programa. |
| `.github/workflows/radar.yml` | Cada cuánto se ejecuta. |

## Cómo añadir una fuente

1. Abre `fuentes.yml` y pulsa el lápiz ✏️.
2. Copia un bloque de los que hay y cambia el nombre y la búsqueda (`q`) o la dirección (`url`).
3. Pulsa **Commit changes**.

## Lanzarlo a mano

Pestaña **Actions** → **Radar de baloncesto** → **Run workflow**.
