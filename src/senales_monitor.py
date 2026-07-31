"""
Manejador de señales del monitor de procesos.

Implementa el patrón self-pipe para coordinar señales con el loop principal
de forma async-signal-safe. El handler de señal solo escribe 1 byte en un pipe;
el loop principal lee ese byte y ejecuta la acción real (que puede hacer I/O
bloqueante libremente porque ya no estamos en contexto de señal).

Señales manejadas:
  SIGINT / SIGTERM  -> Apagado limpio
  SIGHUP            -> Recarga config.json en caliente
  SIGUSR1           -> Dump del snapshot a dump_<timestamp>.json
  SIGUSR2           -> Toggle modo verbose
  SIGWINCH          -> Repintar la TUI (redimensión de terminal)
"""

import signal
import os
import json
import datetime
import fcntl
import select
import time

# --- Self-Pipe ---
# Par de file descriptors: los handlers de señal escriben en _pipe_w (write);
# el loop del monitor lee de _pipe_r (read) y actúa sin problemas de reentrancia.
_pipe_r, _pipe_w = os.pipe()

# Ponemos el extremo de escritura en modo no-bloqueante para que el handler
# sea async-signal-safe (os.write nunca bloquea en un pipe no-bloqueante).
flags = fcntl.fcntl(_pipe_w, fcntl.F_GETFL)
fcntl.fcntl(_pipe_w, fcntl.F_SETFL, flags | os.O_NONBLOCK)


def _handler_generico(signum, frame):
    """Handler mínimo: solo escribe el número de señal en el pipe. 100% async-signal-safe."""
    try:
        os.write(_pipe_w, bytes([signum]))
    except BlockingIOError:
        pass  # El pipe está lleno (muy raro), ignoramos silenciosamente


def registrar_handlers():
    """Registra los handlers de señal. Debe llamarse en el proceso principal."""
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP,
                signal.SIGUSR1, signal.SIGUSR2, signal.SIGWINCH):
        signal.signal(sig, _handler_generico)


# --- Acciones reales (ejecutadas fuera del contexto de señal) ---

def accion_apagado(evento_apagado):
    """SIGINT / SIGTERM: apagado limpio."""
    print("\n[Monitor] Señal de apagado recibida. Cerrando...", flush=True)
    evento_apagado.set()


def accion_recargar_config(intervalos, snapshot_global):
    """SIGHUP: recarga config.json y actualiza los intervalos en memoria compartida."""
    try:
        with open("config.json", "r") as f:
            cfg = json.load(f)
        ivs = cfg.get("intervalos", {})
        for vista, val in ivs.items():
            if vista in intervalos:
                intervalos[vista].value = float(val)
        
        # Guardamos la notificación para la TUI
        msg = f"SIGHUP: config.json recargado."
        snapshot_global["notificacion"] = {"msg": msg, "ts": time.time()}
        
    except (FileNotFoundError, json.JSONDecodeError) as e:
        msg = f"SIGHUP: error al leer config.json — {e}"
        snapshot_global["notificacion"] = {"msg": msg, "ts": time.time()}


def accion_dump_snapshot(snapshot_global):
    """SIGUSR1: serializa el snapshot actual a dump_<timestamp>.json."""
    try:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre = f"dump_{ts}.json"

        # Manager.dict no es directamente serializable; lo convertimos a dict normal
        def convertir(obj):
            if hasattr(obj, 'items'):
                return {k: convertir(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convertir(i) for i in obj]
            else:
                return obj

        datos = convertir(snapshot_global)
        with open(nombre, "w") as f:
            json.dump(datos, f, indent=2, default=str)
        
        msg = f"SIGUSR1: snapshot guardado en {nombre}"
        snapshot_global["notificacion"] = {"msg": msg, "ts": time.time()}
    except Exception as e:
        msg = f"SIGUSR1: error al dumpear snapshot — {e}"
        snapshot_global["notificacion"] = {"msg": msg, "ts": time.time()}


# Variable de modo verbose (compartida mediante multiprocessing.Value en main.py)
_verbose_val = None

def set_verbose_value(val):
    """Guarda la referencia al Value compartido de verbose."""
    global _verbose_val
    _verbose_val = val


def accion_toggle_verbose(snapshot_global):
    """SIGUSR2: activa/desactiva el modo verbose."""
    if _verbose_val is not None:
        _verbose_val.value = 0 if _verbose_val.value else 1
        estado = "ON" if _verbose_val.value else "OFF"
        msg = f"SIGUSR2: modo verbose {estado}"
        snapshot_global["notificacion"] = {"msg": msg, "ts": time.time()}


# --- Loop de despacho ---

def loop_senales(evento_apagado, intervalos, snapshot_global):
    """
    Loop que corre en el proceso principal, leyendo el pipe de señales.
    Bloquea hasta que llega una señal o hasta que evento_apagado está activo.
    """
    while not evento_apagado.is_set():
        # Esperamos hasta 1 segundo para que el loop sea interrumpible
        readable, _, _ = select.select([_pipe_r], [], [], 1.0)
        if not readable:
            continue

        try:
            datos = os.read(_pipe_r, 32)  # Leemos hasta 32 señales acumuladas
        except OSError:
            continue

        for signum in datos:
            if signum == signal.SIGHUP:
                accion_recargar_config(intervalos, snapshot_global)
            elif signum == signal.SIGUSR1:
                accion_dump_snapshot(snapshot_global)
            elif signum == signal.SIGUSR2:
                accion_toggle_verbose(snapshot_global)
            elif signum in (signal.SIGINT, signal.SIGTERM):
                msg = "Señal de apagado recibida, terminando..."
                snapshot_global["notificacion"] = {"msg": msg, "ts": time.time()}
                accion_apagado(evento_apagado)
            elif signum == signal.SIGWINCH:
                # La TUI con Rich/Live se repinta sola al leer el nuevo tamaño
                pass
