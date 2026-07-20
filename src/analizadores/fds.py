import os
import time

def analizador_fds(snapshot_global, evento_apagado):
    print("[FDs] Analizador iniciado...")
    intervalo = 5
    
    while not evento_apagado.is_set():
        pids = snapshot_global["sistema"].get("pids_activos", [])
        fds_local = {}
        
        for pid in pids:
            try:
                # Contamos cuántos elementos hay dentro de la carpeta fd
                archivos_abiertos = os.listdir(f"/proc/{pid}/fd")
                cantidad = len(archivos_abiertos)
                
                fds_local[pid] = {"cantidad": cantidad}
                
            except (FileNotFoundError, PermissionError):
                # Ignoramos si el proceso murió (FileNotFound) 
                # o si Linux nos prohíbe espiarlo (PermissionError)
                continue
                
        snapshot_global["fds"] = fds_local
        time.sleep(intervalo)