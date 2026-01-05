# DRONEX Agent

Agente Python para ejecutar en un companion computer (Raspberry Pi / Jetson) y conectarse al backend DRONEX expuesto por ngrok.

## Requisitos

- Python 3.11
- Linux (probado en Raspberry Pi/Jetson, pero puede correr en PC para pruebas)

## Instalación

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuración

Copia el archivo de ejemplo y ajusta los valores:

```bash
cp config.example.json config.json
```

Campos requeridos:

- `DRONEX_URL`: URL HTTPS de ngrok (ej. `https://xxxx.ngrok-free.app`)
- `DRONE_ID`: identificador de dron (ej. `DRX-001`)
- `DRONE_TOKEN`: token seguro (no se imprime en logs)
- `MODE`: `SIMULATION` | `MAVLINK`
- `TELEMETRY_INTERVAL`: segundos entre envíos

## Ejecución

```bash
python agent.py --config config.json
```

## Pruebas contra ngrok

1. Asegura que el backend DRONEX esté levantado y expuesto por ngrok.
2. Verifica que el endpoint `https://<tu-ngrok>/api/agent/register/` responda.
3. Ejecuta el agente y valida los logs de registro y telemetría.

## Notas

- El agente usa HTTPS obligatorio por seguridad.
- Maneja reconexiones automáticamente.
- Modo MAVLink aún no implementado (estructura lista para futura integración).
