"""Motor de traduccion con la API de Anthropic (Claude), usando el SDK oficial `anthropic`.

Configuracion (entorno o .env), con SUBTRAD_API_FORMATO=anthropic:
- SUBTRAD_API_KEY: clave (si falta se usa ANTHROPIC_API_KEY).
- SUBTRAD_API_URL: base de la API solo si no es la oficial (ej. un gateway compatible con el formato de Anthropic).
- SUBTRAD_MODELO: por defecto claude-haiku-5-5, el mas barato y suficiente para traducir.
- SUBTRAD_ESFUERZO: low / medium / high (por defecto medium).

Tiene la misma interfaz que motor_api.MotorAPI (completar, uso, modelo, url), asi traducir_capitulo sirve para los dos.
La API ya no acepta temperature, asi que no se envia; la profundidad se controla con el esfuerzo.
"""
import anthropic

from subtrad import config
from subtrad.motor_api import ErrorAPI, Uso

MODELO_POR_DEFECTO = 'claude-haiku-5-5'
MAX_TOKENS = 16000


class MotorAnthropic:
    """Cliente de Messages API para traducir parte por parte."""

    def __init__(self, modelo : str|None = None, url : str|None = None, clave : str|None = None, esfuerzo : str|None = None):
        clave = clave or config.valor('SUBTRAD_API_KEY') or config.valor('ANTHROPIC_API_KEY')
        if not clave:
            raise ErrorAPI('Falta la clave: SUBTRAD_API_KEY (o ANTHROPIC_API_KEY) en .env')
        self.url = url or config.valor('SUBTRAD_API_URL') or 'https://api.anthropic.com'
        self.modelo = modelo or config.valor('SUBTRAD_MODELO') or MODELO_POR_DEFECTO
        self.esfuerzo = esfuerzo or config.valor('SUBTRAD_ESFUERZO', 'medium')
        self.uso = Uso()
        # El SDK ya reintenta 429, 5xx y errores de conexion con espera exponencial
        self.cliente = anthropic.Anthropic(api_key=clave, base_url=self.url, max_retries=4)

    def completar(self, mensajes : list[dict]) -> str:
        """Mismo formato de mensajes que la API de OpenAI: el primero es el de sistema."""
        sistema = '\n\n'.join(m['content'] for m in mensajes if m['role'] == 'system')
        conversacion = [m for m in mensajes if m['role'] != 'system']
        try:
            respuesta = self.cliente.messages.create(
                model=self.modelo,
                max_tokens=MAX_TOKENS,
                system=sistema,
                messages=conversacion,
                output_config={'effort': self.esfuerzo},
            )
        except anthropic.AuthenticationError as error:
            raise ErrorAPI(f'Clave rechazada por {self.url}') from error
        except anthropic.NotFoundError as error:
            raise ErrorAPI(f'Modelo o direccion inexistente ({self.modelo} en {self.url})') from error
        except anthropic.APIStatusError as error:
            raise ErrorAPI(f'HTTP {error.status_code}: {str(error.message)[:300]}') from error
        except anthropic.APIConnectionError as error:
            raise ErrorAPI(f'Sin conexion con {self.url}') from error

        if respuesta.stop_reason == 'refusal':
            raise ErrorAPI('El modelo rechazo traducir esta parte')
        if respuesta.stop_reason == 'max_tokens':
            raise ErrorAPI('La respuesta se corto por largo: usar partes mas chicas (--lineas)')

        self.uso.entrada += respuesta.usage.input_tokens
        self.uso.salida += respuesta.usage.output_tokens
        return ''.join(bloque.text for bloque in respuesta.content if bloque.type == 'text')
