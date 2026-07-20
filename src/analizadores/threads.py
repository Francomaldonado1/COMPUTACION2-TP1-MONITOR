import os
import time

def analizador_threads(snapshot_global, evento_apagado):
    print("[Threads] Analizador iniciado...")
    intervalo = 2

    while not evento_apagado.is_set():
        pids = snapshot_global["sistema"].get("pids_activos", [])
        threads_local = {}

        for pid in pids:
            try:
                # Contamos cuántos elementos hay dentro de la carpeta task
                hilos = os.listdir(f"/proc/{pid}/task")
                cantidad_hilos = len(hilos)

                threads_local[pid] = {"cantidad": cantidad_hilos}

            except (FileNotFoundError, PermissionError):
                # Ignoramos si el proceso murió (FileNotFound) 
                # o si Linux nos prohíbe espiarlo (PermissionError)
                continue

        snapshot_global["threads"] = threads_local
        time.sleep(intervalo)
        