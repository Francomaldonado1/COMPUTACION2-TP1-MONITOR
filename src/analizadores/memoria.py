import time
import os


# --- FUNCIÓN AUXILIAR ---
# La separamos del bucle principal para que sea fácil de leer y testear sola.
def leer_segmentos_maps(pid):
    """
    Lee /proc/<pid>/maps y agrupa las regiones de memoria en categorías:
    text, data, heap, stack, shared.

    Reglas de clasificación (en orden de prioridad):
    1. Si el 4to carácter del permiso es 's' → shared (memoria compartida sin COW)
    2. Si la etiqueta es [heap]              → heap
    3. Si la etiqueta es [stack]             → stack
    4. Si los permisos contienen 'x'         → text (código ejecutable)
    5. Todo lo demás                         → data (variables, constantes, etc.)

    Devuelve un dict con el total de BYTES de cada categoría.
    """
    segmentos = {"text": 0, "data": 0, "heap": 0, "stack": 0, "shared": 0}

    try:
        with open(f"/proc/{pid}/maps", "r") as f:
            for linea in f:
                partes = linea.split()

                # Cada línea tiene al menos 5 columnas: rango perms offset dev inode [pathname]
                if len(partes) < 5:
                    continue

                rango    = partes[0]  # ej: "7f8a1c000000-7f8a1c200000"
                perms    = partes[1]  # ej: "r-xp"
                etiqueta = partes[5] if len(partes) >= 6 else ""  # ej: "[heap]" o "/usr/lib/..."

                # Calculamos el tamaño de esta región en bytes.
                # Las direcciones están en hexadecimal (base 16), por eso int(..., 16)
                inicio, fin = rango.split("-")
                tamanio = int(fin, 16) - int(inicio, 16)

                # Clasificamos la región según las reglas definidas arriba
                if perms[3] == "s":
                    # La 4ta letra es 's': región compartida entre procesos (sin COW)
                    segmentos["shared"] += tamanio
                elif etiqueta == "[heap]":
                    segmentos["heap"] += tamanio
                elif etiqueta == "[stack]":
                    segmentos["stack"] += tamanio
                elif "x" in perms:
                    # Tiene permiso de ejecución: es código (text segment)
                    segmentos["text"] += tamanio
                else:
                    # Resto: datos de solo lectura, variables globales, etc.
                    segmentos["data"] += tamanio

    except (FileNotFoundError, PermissionError):
        # El proceso murió entre el momento en que lo listamos y ahora, o no tenemos permiso
        pass

    return segmentos


# --- ANALIZADOR PRINCIPAL ---
def analizador_memoria(snapshot_global, evento_apagado):
    print("[Memoria] Analizador iniciado...")
    intervalo = 3

    # Los campos que nos interesan de /proc/<pid>/status
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

                # --- BLOQUE 1: /proc/<pid>/status (consumo de RAM) ---
                with open(f"/proc/{pid}/status", "r") as f:
                    for linea in f:
                        if linea.startswith(campos_buscados):
                            partes = linea.split()
                            # Quitamos el ":" del nombre del campo: "VmRSS:" → "VmRSS"
                            clave = partes[0].replace(":", "")
                            # El valor viene en kB, lo guardamos como int
                            datos_pid[clave] = int(partes[1])

                # --- BLOQUE 2: /proc/<pid>/stat (page faults) ---
                # El archivo stat tiene UNA sola línea con todos los campos separados por espacios.
                # La consigna dice "campos 10-13". Como /proc cuenta desde 1 y Python desde 0,
                # el campo 10 de /proc es el índice 9 en Python.
                with open(f"/proc/{pid}/stat", "r") as f:
                    partes_stat = f.readline().split()

                    datos_pid["min_flt"]  = int(partes_stat[9])   # minor faults del proceso
                    datos_pid["cmin_flt"] = int(partes_stat[10])  # minor faults acumulados (hijos)
                    datos_pid["maj_flt"]  = int(partes_stat[11])  # major faults del proceso
                    datos_pid["cmaj_flt"] = int(partes_stat[12])  # major faults acumulados (hijos)

                # --- BLOQUE 3: /proc/<pid>/maps (segmentos agrupados) ---
                # Llamamos a nuestra función auxiliar definida arriba
                datos_pid["segmentos"] = leer_segmentos_maps(pid)

                if datos_pid:
                    memoria_local[pid] = datos_pid

            except (FileNotFoundError, PermissionError, IndexError, ValueError):
                # FileNotFoundError: el proceso murió mientras lo leíamos
                # PermissionError:   no tenemos permiso para espiar ese proceso
                # IndexError:        el archivo stat estaba incompleto (proceso muy efímero)
                # ValueError:        algún campo no era un número válido
                continue

        # Reasignamos el dict completo para que el Manager propague el cambio a todos los procesos
        snapshot_global["memoria"] = memoria_local
        time.sleep(intervalo)