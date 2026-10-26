# Traductor de series y peliculas

Traduce subtitulos de series y peliculas con IA, respetando los nombres y el glosario de cada serie.
Pensado para bibliotecas de Plex: deja el subtitulo traducido al lado del video (`episodio.es.ass`) para que Plex lo detecte solo.

> Estado: en construccion. El plan completo esta en [docs/PLAN.md](docs/PLAN.md).

## Que hace

- Saca los subtitulos en ingles que vienen dentro del video (mkv/mp4).
- Traduce solo el texto: tiempos, estilos y posiciones quedan intactos.
- Respeta un perfil por serie: nombres que no se traducen, lectura de los nombres, tratamiento (tu/usted), unidades militares, etc.
- Controla la calidad: lineas corridas, tags perdidos, partes sin traducir, nombres mal traducidos.
- Funciona con distintos motores de IA: Claude Code, OpenCode o una API compatible con OpenAI.

## Requisitos

- Python 3.10+
- ffmpeg y ffprobe en el PATH (en Windows: `winget install Gyan.FFmpeg`)

## Licencia

MIT. Ver [LICENSE](LICENSE).
