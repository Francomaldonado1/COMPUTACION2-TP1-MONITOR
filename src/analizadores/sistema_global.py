import os
import time

def analizador_sistema_global(snapshot_global, evento_apagado, intervalo_val):
    print("[Global System] Analizador iniciado...")
    
    historial_cpu = {}

    while not evento_apagado.is_set():
        stats = {}
        
        # 1. Load average (/proc/loadavg)
        try:
            with open("/proc/loadavg", "r") as f:
                stats["loadavg"] = " ".join(f.read().split()[:3])
        except Exception:
            stats["loadavg"] = "-"

        # 2. Uptime (/proc/uptime)
        try:
            with open("/proc/uptime", "r") as f:
                stats["uptime"] = float(f.read().split()[0])
        except Exception:
            stats["uptime"] = 0

        # 3. CPU Global & Btime (/proc/stat)
        try:
            with open("/proc/stat", "r") as f:
                for line in f:
                    if line.startswith("cpu "):
                        campos = [int(x) for x in line.split()[1:]]
                        # user, nice, system, idle, iowait, irq, softirq
                        user, nice, system, idle, iowait, irq, softirq = campos[:7]
                        
                        total = user + nice + system + idle + iowait + irq + softirq
                        
                        if "cpu_total" in historial_cpu:
                            prev_campos = historial_cpu["cpu_campos"]
                            prev_total = historial_cpu["cpu_total"]
                            
                            delta_total = total - prev_total
                            
                            if delta_total > 0:
                                stats["cpu_user"] = round((user - prev_campos[0]) / delta_total * 100, 2)
                                stats["cpu_system"] = round((system - prev_campos[2]) / delta_total * 100, 2)
                                stats["cpu_idle"] = round((idle - prev_campos[3]) / delta_total * 100, 2)
                                stats["cpu_iowait"] = round((iowait - prev_campos[4]) / delta_total * 100, 2)
                            else:
                                stats["cpu_user"] = stats["cpu_system"] = stats["cpu_idle"] = stats["cpu_iowait"] = 0.0
                        else:
                            stats["cpu_user"] = stats["cpu_system"] = stats["cpu_idle"] = stats["cpu_iowait"] = 0.0
                            
                        historial_cpu["cpu_total"] = total
                        historial_cpu["cpu_campos"] = campos
                    elif line.startswith("btime "):
                        stats["btime"] = int(line.split()[1])
        except Exception:
            stats["cpu_user"] = stats["cpu_system"] = stats["cpu_idle"] = stats["cpu_iowait"] = 0.0
            stats["btime"] = 0

        # 4. Meminfo (/proc/meminfo)
        mem_info = {}
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    partes = line.split()
                    if partes[0] == "MemTotal:": mem_info["MemTotal"] = int(partes[1])
                    elif partes[0] == "MemFree:": mem_info["MemFree"] = int(partes[1])
                    elif partes[0] == "Buffers:": mem_info["Buffers"] = int(partes[1])
                    elif partes[0] == "Cached:": mem_info["Cached"] = int(partes[1])
                    elif partes[0] == "SwapTotal:": mem_info["SwapTotal"] = int(partes[1])
                    elif partes[0] == "SwapFree:": mem_info["SwapFree"] = int(partes[1])
        except Exception:
            pass
        stats["meminfo"] = mem_info

        # 5. Contar estados de procesos recorriendo /proc/<pid>/stat
        pids = snapshot_global["sistema"].get("pids_activos", [])
        estados = {"R": 0, "S": 0, "D": 0, "Z": 0, "T": 0, "total": len(pids), "threads": 0}
        
        for pid in pids:
            try:
                with open(f"/proc/{pid}/stat", "r") as f:
                    linea = f.read()
                idx = linea.rfind(')')
                if idx != -1:
                    campos = linea[idx+2:].split()
                    estado = campos[0]
                    # El campo de threads es el 20 en proc, índice 17 tras nuestro split(idx+2)
                    num_threads = int(campos[17]) 
                    
                    estados["threads"] += num_threads
                    if estado in estados:
                        estados[estado] += 1
                    else:
                        estados[estado] = 1
            except Exception:
                continue
                
        stats["estados"] = estados
        
        # Guardamos todo en memoria compartida
        snapshot_global["sistema_global"] = stats
        time.sleep(intervalo_val.value)
