#!/usr/bin/env python3
import argparse
import json
import logging
import os
import random
import socket
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

import platform

import psutil
import requests


AGENT_VERSION = "1.0.0"
DEFAULT_TELEMETRY_INTERVAL = 5
REGISTER_RETRY_SECONDS = 10
DEFAULT_TIMEOUT = 10


class ConfigError(Exception):
    pass


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("dronex_agent")
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler("agent.log")
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger


def load_config(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise ConfigError(f"Config file not found: {path}")

    ext = os.path.splitext(path)[1].lower()
    if ext in {".json", ""}:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    if ext in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ConfigError(
                "PyYAML is required for YAML configs. Install pyyaml or use JSON config."
            ) from exc

        with open(path, "r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)

    raise ConfigError("Config must be .json or .yaml")


def validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    required_keys = {
        "DRONEX_URL",
        "DRONE_ID",
        "DRONE_TOKEN",
        "MODE",
        "TELEMETRY_INTERVAL",
    }
    missing = required_keys - set(config.keys())
    if missing:
        raise ConfigError(f"Missing config keys: {', '.join(sorted(missing))}")

    dronex_url = str(config["DRONEX_URL"]).rstrip("/")
    if not dronex_url.startswith("https://"):
        raise ConfigError("DRONEX_URL must start with https://")

    mode = str(config["MODE"]).upper()
    if mode not in {"SIMULATION", "MAVLINK"}:
        raise ConfigError("MODE must be SIMULATION or MAVLINK")

    interval = int(config.get("TELEMETRY_INTERVAL", DEFAULT_TELEMETRY_INTERVAL))
    if interval <= 0:
        raise ConfigError("TELEMETRY_INTERVAL must be > 0")

    return {
        **config,
        "DRONEX_URL": dronex_url,
        "MODE": mode,
        "TELEMETRY_INTERVAL": interval,
    }


def get_system_info() -> Dict[str, Any]:
    hostname = socket.gethostname()
    os_info = f"{platform.system()} {platform.release()}"
    cpu_info = platform.processor() or f"cpu_count:{psutil.cpu_count(logical=True)}"
    ram_mb = int(psutil.virtual_memory().total / (1024 * 1024))
    return {
        "hostname": hostname,
        "os": os_info,
        "cpu": cpu_info,
        "ram_mb": ram_mb,
    }


def build_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": f"DRONEX-Agent/{AGENT_VERSION}",
    }


def register_agent(session: requests.Session, config: Dict[str, Any], logger: logging.Logger) -> None:
    url = f"{config['DRONEX_URL']}/api/agent/register/"
    payload = {
        "drone_id": config["DRONE_ID"],
        "agent_version": AGENT_VERSION,
        "mode": config["MODE"],
        "system": get_system_info(),
    }

    while True:
        try:
            response = session.post(
                url,
                headers=build_headers(config["DRONE_TOKEN"]),
                json=payload,
                timeout=DEFAULT_TIMEOUT,
            )
            if response.status_code == 200:
                logger.info("Registro exitoso en DRONEX")
                return
            logger.error(
                "Registro falló (%s): %s", response.status_code, response.text.strip()
            )
        except requests.RequestException as exc:
            logger.warning("Error de red al registrar: %s", exc)

        logger.info("Reintentando registro en %s segundos...", REGISTER_RETRY_SECONDS)
        time.sleep(REGISTER_RETRY_SECONDS)


def generate_simulated_telemetry(battery: float) -> Dict[str, Any]:
    base_lat = 4.658
    base_lng = -74.093
    lat_offset = random.uniform(-0.0005, 0.0005)
    lng_offset = random.uniform(-0.0005, 0.0005)

    return {
        "lat": base_lat + lat_offset,
        "lng": base_lng + lng_offset,
        "alt": round(random.uniform(80, 120), 2),
        "speed": round(random.uniform(0, 15), 2),
        "battery": round(battery, 2),
        "signal": round(random.uniform(70, 100), 2),
        "heading": round(random.uniform(0, 360), 2),
        "status": "IN_OPERATION",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def telemetry_loop(session: requests.Session, config: Dict[str, Any], logger: logging.Logger) -> None:
    url = f"{config['DRONEX_URL']}/api/agent/telemetry/"
    interval = config["TELEMETRY_INTERVAL"]
    battery = 100.0

    while True:
        telemetry = generate_simulated_telemetry(battery)
        payload = {
            "drone_id": config["DRONE_ID"],
            **telemetry,
        }

        try:
            response = session.post(
                url,
                headers=build_headers(config["DRONE_TOKEN"]),
                json=payload,
                timeout=DEFAULT_TIMEOUT,
            )
            if response.status_code == 200:
                logger.info("Telemetría enviada correctamente")
            else:
                logger.error(
                    "Telemetría falló (%s): %s",
                    response.status_code,
                    response.text.strip(),
                )
        except requests.RequestException as exc:
            logger.warning("Error de red al enviar telemetría: %s", exc)

        battery = max(battery - random.uniform(0.5, 1.5), 0)
        time.sleep(interval)


# FUTURO:
# - Integración MAVLink via pymavlink o MAVSDK.
# - WebSocket para recepción de comandos en tiempo real.

def main() -> None:
    parser = argparse.ArgumentParser(description="DRONEX Agent")
    parser.add_argument("--config", required=True, help="Ruta a config.json o config.yaml")
    args = parser.parse_args()

    logger = setup_logging()

    try:
        config = validate_config(load_config(args.config))
    except (ConfigError, json.JSONDecodeError) as exc:
        logger.error("Error en configuración: %s", exc)
        raise SystemExit(1) from exc

    logger.info("Iniciando DRONEX Agent %s", AGENT_VERSION)
    logger.info("DRONE_ID: %s", config["DRONE_ID"])
    logger.info("MODE: %s", config["MODE"])

    session = requests.Session()
    session.headers.update({"X-Agent-Session": str(uuid.uuid4())})

    register_agent(session, config, logger)

    if config["MODE"] == "SIMULATION":
        telemetry_loop(session, config, logger)
    else:
        logger.error("MAVLINK mode no implementado aún. Usa SIMULATION.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
