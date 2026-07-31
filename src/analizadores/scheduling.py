import os
import time

POLITICAS = {
    "0": "OTHER (0)",
    "1": "FIFO (1)",
    "2": "RR (2)",
    "3": "BATCH (3)",
    "5": "IDLE (5)",
    "6": "DEADLINE (6)"
}

def analizador_scheduling(snapshot_global, evento_apagado, intervalo_val):
    print("[Scheduling] Analizador iniciado...")
    hertz = os.sysconf("SC_CLK_TCK")

    while not evento_apagado.is_set():
        pids = snapshot_global["sistema"].get("pids_activos", [])
        scheduling_local = {}
        
        for pid in pids:
            try:
                # 1. Leer de /proc/<pid>/stat
                with open(f"/proc/{pid}/stat", "r") as f:
                    linea = f.read()
                
                # El campo 2 (comm) está entre paréntesis y puede tener espacios.
                # Cortamos desde el último paréntesis cerrado para evitar que el split() se rompa.
                idx_cierre = linea.rfind(')')
                if idx_cierre != -1:
                    campos = linea[idx_cierre + 2:].split()
                    # Ahora campos[0] es el campo 3 (State) del manual de proc.
                    # Para encontrar el campo N, usamos el índice: N - 3
                    
                    pgrp = campos[5 - 3]         # Campo 5
                    sid = campos[6 - 3]          # Campo 6
                    utime_ticks = int(campos[14 - 3])
                    stime_ticks = int(campos[15 - 3])
                    prioridad = campos[18 - 3]   # Campo 18
                    nice = campos[19 - 3]        # Campo 19
                    
                    # Estos campos pueden no existir en kernels muy viejos, manejamos la excepción
                    try:
                        rt_prio = campos[40 - 3] # Campo 40
                        policy = campos[41 - 3]  # Campo 41
                    except IndexError:
                        rt_prio = "-"
                        policy = "-"
                        
                    utime_seg = utime_ticks / hertz
                    stime_seg = stime_ticks / hertz
                else:
                    continue

                # 2. Leer de /proc/<pid>/status
                cpu_affinity = "-"
                vol_cs = "0"
                invol_cs = "0"
                
                with open(f"/proc/{pid}/status", "r") as f:
                    for l in f:
                        if l.startswith("Cpus_allowed_list:"):
                            cpu_affinity = l.split()[1]
                        elif l.startswith("voluntary_ctxt_switches:"):
                            vol_cs = l.split()[1]
                        elif l.startswith("nonvoluntary_ctxt_switches:"):
                            invol_cs = l.split()[1]

                scheduling_local[pid] = {
                    "nice": nice,
                    "prioridad": prioridad,
                    "politica": POLITICAS.get(policy, policy),
                    "rt_prio": rt_prio,
                    "affinity": cpu_affinity,
                    "vol_cs": vol_cs,
                    "invol_cs": invol_cs,
                    "utime": round(utime_seg, 2),
                    "stime": round(stime_seg, 2),
                    "sid": sid,
                    "pgid": pgrp
                }
                
            except (FileNotFoundError, PermissionError):
                continue
                
        snapshot_global["scheduling"] = scheduling_local
        time.sleep(intervalo_val.value)
