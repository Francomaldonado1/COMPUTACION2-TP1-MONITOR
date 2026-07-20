import os
import time

def analizador_cpu(snapshot_global, evento_apagado):
    print("[CPU/Estado] Analizador iniciado...")
    intervalo = 2
    
    # El procesador de Linux se mide en "Hertz" (ticks por segundo). Suele ser 100.
    hertz = os.sysconf(os.sysconf_names['SC_CLK_TCK'])
    
    # Acá guardamos la "foto anterior" de cada proceso para calcular la diferencia
    # Formato: { pid: (ticks_totales, tiempo_medicion) }
    historial = {}

    while not evento_apagado.is_set():
        pids = snapshot_global["sistema"].get("pids_activos", [])
        cpu_local = {}
        tiempo_actual = time.time()

        for pid in pids:
            try:
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
                
                cpu_local[pid] = {
                    "estado": estado,
                    "cpu_percent": round(cpu_porcentaje, 2)
                }

            except (FileNotFoundError, IndexError):
                # Si el proceso murió, lo borramos de nuestro historial para no juntar basura
                if pid in historial:
                    del historial[pid]
                continue

        snapshot_global["cpu_estado"] = cpu_local
        time.sleep(intervalo)