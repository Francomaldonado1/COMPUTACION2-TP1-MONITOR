import os
import time

def analizador_threads(snapshot_global, evento_apagado):
    print("[Threads] Analizador iniciado...")
    intervalo = 2
    hertz = os.sysconf("SC_CLK_TCK")  # jiffies por segundo (normalmente 100)

    # Historial de ticks por (pid, tid) para calcular el delta de CPU
    # Formato: { (pid, tid): (ticks_totales, tiempo_medicion) }
    historial = {}

    while not evento_apagado.is_set():
        pids = snapshot_global["sistema"].get("pids_activos", [])
        threads_local = {}
        tiempo_actual = time.time()

        for pid in pids:
            try:
                hilos = os.listdir(f"/proc/{pid}/task")
                cantidad_hilos = len(hilos)

                # Inicializamos ANTES del for th para poder hacer append dentro
                threads_local[pid] = {
                    "cantidad": cantidad_hilos,
                    # Primeros 10 hilos con detalle — misma decisión que en FDs
                    "hilos": [],
                }

                for tid in sorted(hilos, key=int):
                    # Dejamos de acumular detalles una vez que tenemos 10
                    if len(threads_local[pid]["hilos"]) >= 10:
                        break

                    try:
                        # --- BLOQUE 1: /proc/<pid>/task/<tid>/stat ---
                        # Campo 3 (índice 2) = estado, campos 14-15 (índices 13-14) = utime/stime
                        with open(f"/proc/{pid}/task/{tid}/stat", "r") as f:
                            campos = f.readline().split()

                        estado_char = campos[2]           # R / S / D / T / Z
                        utime = int(campos[13])           # ticks en espacio de usuario
                        stime = int(campos[14])           # ticks en espacio de kernel
                        ticks = utime + stime

                        # Delta de CPU para este hilo respecto al ciclo anterior
                        cpu_pct = 0.0
                        clave = (pid, int(tid))
                        if clave in historial:
                            ticks_ant, tiempo_ant = historial[clave]
                            delta_ticks  = ticks - ticks_ant
                            delta_tiempo = tiempo_actual - tiempo_ant
                            if delta_tiempo > 0:
                                cpu_pct = 100.0 * (delta_ticks / hertz) / delta_tiempo
                        historial[clave] = (ticks, tiempo_actual)

                        # --- BLOQUE 2: /proc/<pid>/task/<tid>/comm ---
                        # Contiene solo el nombre del hilo (max 16 chars), con \n al final
                        with open(f"/proc/{pid}/task/{tid}/comm", "r") as f:
                            nombre = f.readline().strip()

                        # --- BLOQUE 3: /proc/<pid>/task/<tid>/status (context switches) ---
                        vol_cs, invol_cs = 0, 0
                        with open(f"/proc/{pid}/task/{tid}/status", "r") as f:
                            for linea in f:
                                if linea.startswith("voluntary_ctxt_switches:"):
                                    vol_cs = int(linea.split()[1])
                                elif linea.startswith("nonvoluntary_ctxt_switches:"):
                                    invol_cs = int(linea.split()[1])

                        threads_local[pid]["hilos"].append({
                            "tid":      tid,
                            "nombre":   nombre,
                            "estado":   estado_char,
                            "cpu_pct":  round(cpu_pct, 1),
                            "vol_cs":   vol_cs,    # context switches voluntarios
                            "invol_cs": invol_cs,  # context switches no voluntarios
                        })

                    except (FileNotFoundError, PermissionError, ValueError, IndexError):
                        # El hilo murió entre el listdir y la lectura — normal en Linux
                        continue

            except (FileNotFoundError, PermissionError):
                continue

        # Reasignamos el dict completo para que el Manager propague el cambio
        snapshot_global["threads"] = threads_local
        time.sleep(intervalo)