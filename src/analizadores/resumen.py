import time

def analizador_resumen(snapshot_global, evento_apagado):
    print("[Resumen] Analizador iniciado...")
    intervalo = 2 # El resumen suele actualizarse rápido
    
    while not evento_apagado.is_set():
        pids = snapshot_global["sistema"].get("pids_activos", [])
        resumen_local = {}
        
        for pid in pids:
            try:
                comando = ""
                
                # PLAN A: Leemos el comando completo real
                with open(f"/proc/{pid}/cmdline", "r") as f:
                    # Leemos todo y reemplazamos los bytes nulos por espacios
                    cmd_crudo = f.read()
                    if cmd_crudo:
                        comando = cmd_crudo.replace('\x00', ' ').strip()
                
                # PLAN B: Si está vacío (procesos del kernel), sacamos el nombre de status
                if not comando:
                    with open(f"/proc/{pid}/status", "r") as f:
                        for linea in f:
                            if linea.startswith("Name:"):
                                # Le ponemos corchetes para saber que es un proceso del sistema
                                comando = f"[{linea.split()[1]}]" 
                                break
                
                if comando:
                    # Por ahora solo guardamos el comando, después le sumaremos el usuario y estado
                    resumen_local[pid] = {"comando": comando}
                    
            except (FileNotFoundError, IndexError):
                continue
                
        snapshot_global["resumen"] = resumen_local
        time.sleep(intervalo)