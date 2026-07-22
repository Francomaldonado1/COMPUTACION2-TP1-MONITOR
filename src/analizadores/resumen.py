import time
import os
import pwd


def analizador_resumen(snapshot_global, evento_apagado):
    print("[Resumen] Analizador iniciado...")
    intervalo = 2 # El resumen suele actualizarse rápido

    # El procesador de Linux se mide en "Hertz" (ticks por segundo). Suele ser 100.
    hertz = os.sysconf(os.sysconf_names['SC_CLK_TCK'])
    
    # Acá guardamos la "foto anterior" de cada proceso para calcular la diferencia
    # Formato: { pid: (ticks_totales, tiempo_medicion) }
    historial = {}
    
    while not evento_apagado.is_set():
        pids = snapshot_global["sistema"].get("pids_activos", [])
        resumen_local = {}
        
        for pid in pids:

            try:

                tiempo_actual = time.time()

                with open(f"/proc/{pid}/stat", "r") as f:
                    linea = f.read()
                    
                # Separamos esa línea larguísima por los espacios
                campos = linea.split()
                
                # Extraemos los datos clave
                estado = campos[2]
                utime = int(campos[13])
                stime = int(campos[14])
                
                ticks_totales = utime + stime
                cpu_porcentaje = 0.0

                # MATEMÁTICA DE CPU: Si ya lo habíamos medido antes, calculamos la diferencia
                if pid in historial:
                    ticks_anteriores, tiempo_anterior = historial[pid]
                    delta_ticks = ticks_totales - ticks_anteriores
                    delta_tiempo = tiempo_actual - tiempo_anterior
                    
                    # Fórmula de CPU de Linux: (ticks_gastados / hertz) / segundos_pasados
                    if delta_tiempo > 0:
                        segundos_cpu = delta_ticks / hertz
                        cpu_porcentaje = 100 * (segundos_cpu / delta_tiempo)

                # Guardamos la foto actual para la próxima vuelta
                historial[pid] = (ticks_totales, tiempo_actual)

                # Leemos /proc/<pid>/status SIEMPRE: PPid, Uid y nombre de respaldo
                ppid, uid, nombre_kernel = "?", "?", ""
                with open(f"/proc/{pid}/status", "r") as f:
                    for linea in f:
                        if linea.startswith("PPid:"):
                            ppid = linea.split()[1]
                        elif linea.startswith("Uid:"):
                            uid = linea.split()[1]   # UID real (col 0 de los 4 UIDs)
                            try:
                                nombre = pwd.getpwuid(int(uid)).pw_name
                                usuario = f"{nombre} ({uid})"
                            except (KeyError, ValueError):
                                usuario = uid  # Si no lo encuentra, mostramos el número
                        elif linea.startswith("Name:"):
                            nombre_kernel = linea.split()[1]

                # Leemos /proc/<pid>/cmdline (Plan A: procesos normales)
                # Si está vacío (procesos del kernel), usamos el nombre de status
                with open(f"/proc/{pid}/cmdline", "r") as f:
                    cmd_crudo = f.read()
                    if cmd_crudo:
                        comando = cmd_crudo.replace('\x00', ' ').strip()
                    else:
                        comando = f"[{nombre_kernel}]"   # Plan B: proceso del kernel

                if comando:
                    resumen_local[pid] = {
                        "comando":     comando,
                        "estado":      estado,
                        "cpu_percent": round(cpu_porcentaje, 2),
                        "ppid":        ppid,
                        "uid":         uid,
                        "usuario":     usuario,
                    }

            except (FileNotFoundError, IndexError):
                continue
                
        snapshot_global["resumen"] = resumen_local
        time.sleep(intervalo)

