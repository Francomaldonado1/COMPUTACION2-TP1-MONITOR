import time
import os

def analizador_memoria(snapshot_global, evento_apagado):
    print("[Memoria] Analizador iniciado...")
    intervalo = 3 
    
    campos_buscados = (
        "VmSize:", "VmRSS:", "VmData:", "VmStk:", 
        "VmExe:", "VmLib:", "VmHWM:", "VmSwap:"
    )
    
    while not evento_apagado.is_set():
        pids = snapshot_global["sistema"].get("pids_activos", [])
        memoria_local = {}
        
        for pid in pids:
            try:
                datos_pid = {}
                
                # --- LECTURA DE STATUS (Consumo de RAM) ---
                with open(f"/proc/{pid}/status", "r") as f:
                    for linea in f:
                        if linea.startswith(campos_buscados):
                            partes = linea.split()
                            clave = partes[0].replace(":", "")
                            datos_pid[clave] = int(partes[1])
                            
                # --- LECTURA DE STAT (Page Faults) ---
                # Leemos la única línea que tiene el archivo
                with open(f"/proc/{pid}/stat", "r") as f:
                    linea_stat = f.readline()
                    partes_stat = linea_stat.split()
                    
                    # La cátedra dice "campos 10-13". 
                    # Como Python cuenta desde 0, los índices reales son 9 al 12.
                    datos_pid["min_flt"] = int(partes_stat[9])
                    datos_pid["cmin_flt"] = int(partes_stat[10])
                    datos_pid["maj_flt"] = int(partes_stat[11])
                    datos_pid["cmaj_flt"] = int(partes_stat[12])

                # TODO: Implementar lectura de /proc/<pid>/maps para los segmentos
                
                if datos_pid:
                    memoria_local[pid] = datos_pid
                    
            except (FileNotFoundError, IndexError):
                # Si el proceso muere en el medio (FileNotFoundError) o el archivo 
                # stat estaba incompleto (IndexError), simplemente seguimos.
                continue
                
        # Reasignamos para que el Manager comparta la info
        snapshot_global["memoria"] = memoria_local
        time.sleep(intervalo)