import os
import time

def inferir_tipo(destino):
    """
    Infiere el tipo de FD a partir del destino del symlink en /proc/<pid>/fd/<n>.
    Retorna siempre un string para garantizar que pipes+sockets+tty+files+other == cantidad.
    """
    if destino.startswith("pipe:"):
        return "pipe"
    elif destino.startswith("socket:"):
        return "socket"
    elif destino.startswith("/dev/pts"):
        return "tty"
    elif destino.startswith("/"):
        return "file"
    else:
        # anon_inode:[eventfd], anon_inode:inotify, etc.
        return "other"

def analizador_fds(snapshot_global, evento_apagado):
    print("[FDs] Analizador iniciado...")
    intervalo = 5

    while not evento_apagado.is_set():
        pids = snapshot_global["sistema"].get("pids_activos", [])
        fds_local = {}

        for pid in pids:
            try:
                archivos_abiertos = os.listdir(f"/proc/{pid}/fd")
                cantidad = len(archivos_abiertos)

                fds_local[pid] = {
                    "cantidad": cantidad,
                    "pipes":    0,
                    "sockets":  0,
                    "tty":      0,
                    "files":    0,
                    "other":    0,
                    # Primeros 10 FDs con su destino y tipo — para mostrar en Vista 3
                    # sin explotar la tabla con cientos de filas por proceso
                    "muestra":  [],
                }

                for fd in sorted(archivos_abiertos, key=int):
                    try:
                        destino = os.readlink(f"/proc/{pid}/fd/{fd}")
                    except (FileNotFoundError, PermissionError):
                        # El FD desapareció entre el listdir y el readlink
                        continue

                    tipo = inferir_tipo(destino)

                    # "pipe"→"pipes", "socket"→"sockets", "file"→"files", "tty"→"tty", "other"→"other"
                    mapa = {"pipe": "pipes", "socket": "sockets", "tty": "tty", "file": "files", "other": "other"}
                    fds_local[pid][mapa[tipo]] += 1

                    # Guardamos en la muestra solo los primeros 10
                    if len(fds_local[pid]["muestra"]) < 10:
                        fds_local[pid]["muestra"].append({
                            "fd":      fd,
                            "destino": destino,
                            "tipo":    tipo,
                        })

            except (FileNotFoundError, PermissionError):
                continue

        snapshot_global["fds"] = fds_local
        time.sleep(intervalo)