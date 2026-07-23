import time
import threading
import sys
import tty
import termios
import select
from rich.live import Live
from rich.table import Table

# Convierte bytes a MB con un decimal y unidad — usada en la Vista 2
def a_mb(bytes_val):
    return f"{bytes_val / (1024 * 1024):.1f} MB"

# Nuestra variable global compartida en la memoria del proceso
vista_activa = '1'

def escuchar_teclado(evento_apagado):
    """Este HILO corre en segundo plano escuchando el teclado sin bloquear la pantalla"""
    global vista_activa
    
    try:
        with open('/dev/tty', 'r') as tty_file:
            fd = tty_file.fileno()
            old_settings = termios.tcgetattr(fd)
            
            try:
                tty.setcbreak(fd)
                while not evento_apagado.is_set():
                    # select escucha el archivo. Si en 0.5 seg no hay teclas, devuelve listas vacías
                    dr, dw, de = select.select([tty_file], [], [], 0.5)
                    
                    if dr: # Si hay datos listos para leer (alguien apretó una tecla)
                        tecla = tty_file.read(1).lower()
                        
                        if tecla in ['1', '2', '3', '4', '5', '6', '7', 'r', 'm', 'f', 't', 's', 'p', 'g']:
                            vista_activa = tecla
                        elif tecla == 'q':
                            evento_apagado.set()
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except Exception as e:
        pass


def generar_tabla(snapshot_global):
    """Esta función decide QUÉ dibujar dependiendo de la vista activa"""
    global vista_activa
    
    # Leemos los datos base (igual que antes)
    pids_activos = snapshot_global.get("sistema", {}).get("pids_activos", [])
    
    if vista_activa in ['1', 'r']:
        tabla = Table(title="Vista 1: Resumen (Estado, CPU, RSS, Threads)", expand=True)
        
        # Columnas
        tabla.add_column("PID",     style="cyan",       justify="right")
        tabla.add_column("PPID",    style="dim cyan",    justify="right")
        tabla.add_column("Usuario", style="green",       justify="left")
        tabla.add_column("Estado",  style="bold green",  justify="center")
        tabla.add_column("Comando", justify="left")
        tabla.add_column("CPU %",   style="yellow",      justify="right")
        tabla.add_column("RSS (KB)",style="magenta",     justify="right")
        tabla.add_column("Hilos",   style="blue",        justify="right")

        # Traemos diccionarios
        pids_activos = snapshot_global.get("sistema", {}).get("pids_activos", [])
        resumen = snapshot_global.get("resumen", {})
        memoria = snapshot_global.get("memoria", {})
        threads = snapshot_global.get("threads", {})
        
        # Filtramos los procesos del kernel (los que no tienen comando)
        pids_validos = [p for p in pids_activos if resumen.get(p, {}).get("comando", "").strip() != ""]
        
        # Ordenamos por Memoria RSS (de mayor a menor)
        pids_ordenados = sorted(
            pids_validos, 
            key=lambda p: memoria.get(p, {}).get("VmRSS", 0), 
            reverse=True
        )
        
        # Nos quedamos solo con el Top 20
        top_20 = pids_ordenados[:20]

        # Iteramos sobre el top 20 en lugar de todos los activos
        for pid in top_20:
            datos_resumen = resumen.get(pid, {})
            datos_memoria = memoria.get(pid, {})
            datos_threads = threads.get(pid, {})

            ppid    = datos_resumen.get("ppid",    "?")
            usuario = datos_resumen.get("usuario",  "?")
            comando = datos_resumen.get("comando", "Cargando...")
            if len(comando) > 45:
                comando = comando[:42] + "..."

            estado         = datos_resumen.get("estado", "-")
            cpu_percent    = f"{datos_resumen.get('cpu_percent', 0.0):.1f} %"
            vmrss          = f"{datos_memoria.get('VmRSS', 0):,}"
            cantidad_hilos = str(datos_threads.get("cantidad", "1"))

            tabla.add_row(str(pid), str(ppid), str(usuario), estado, comando,
                          cpu_percent, vmrss, cantidad_hilos)

    elif vista_activa in ['2', 'm']:
        tabla = Table(title="Vista 2: Memoria (VmRSS, Segmentos, Page Faults)", expand=True)

        # Columnas de identidad del proceso
        tabla.add_column("PID",       style="cyan",    justify="right")
        tabla.add_column("Comando",   justify="left")

        # Columnas de consumo de RAM (de /proc/<pid>/status, en kB)
        tabla.add_column("VmSize",    style="blue",    justify="right")   # Espacio virtual total
        tabla.add_column("VmRSS",     style="magenta", justify="right")   # RAM física usada
        tabla.add_column("VmHWM",     style="red",     justify="right")   # Pico máximo de RSS
        tabla.add_column("VmData",    style="blue",    justify="right")   # Segmento de datos
        tabla.add_column("VmStk",     style="blue",    justify="right")   # Pila (stack)
        tabla.add_column("VmExe",     style="blue",    justify="right")   # Código ejecutable
        tabla.add_column("VmLib",     style="blue",    justify="right")   # Librerías compartidas
        tabla.add_column("VmSwap",    style="yellow",  justify="right")   # En swap

        # Columnas de segmentos mapeados (de /proc/<pid>/maps, convertidos a MB)
        tabla.add_column("Text(MB)",  style="green",   justify="right")   # Código ejecutable
        tabla.add_column("Data(MB)",  style="green",   justify="right")   # Datos (sin heap/stack)
        tabla.add_column("Heap(MB)",  style="green",   justify="right")   # Memoria dinámica
        tabla.add_column("Stack(MB)", style="green",   justify="right")   # Pila de llamadas
        tabla.add_column("Shr(MB)",   style="cyan",    justify="right")   # Regiones compartidas

        # Columnas de page faults (de /proc/<pid>/stat)
        tabla.add_column("MinFlt",    style="dim",     justify="right")   # Minor faults (sin I/O)
        tabla.add_column("MajFlt",    style="bold red",justify="right")   # Major faults (con I/O)

        resumen = snapshot_global.get("resumen", {})
        memoria = snapshot_global.get("memoria", {})

        # Ordenamos por VmRSS descendente y tomamos el Top 20
        pids_validos = [p for p in pids_activos if resumen.get(p, {}).get("comando", "").strip() != ""]
        pids_ordenados = sorted(
            pids_validos,
            key=lambda p: memoria.get(p, {}).get("VmRSS", 0),
            reverse=True
        )
        top_20 = pids_ordenados[:20]

        for pid in top_20:
            datos_resumen = resumen.get(pid, {})
            datos_memoria = memoria.get(pid, {})
            segmentos     = datos_memoria.get("segmentos", {})

            comando = datos_resumen.get("comando", "Cargando...")
            if len(comando) > 30:
                comando = comando[:27] + "..."

            # Valores de /proc/<pid>/status (en kB)
            def kb(clave):
                return f"{datos_memoria.get(clave, 0):,}"

            vmsize = f"{kb('VmSize')} kB"
            vmrss  = f"{kb('VmRSS')} kB"
            vmhwm  = f"{kb('VmHWM')} kB"
            vmdata = f"{kb('VmData')} kB"
            vmstk  = f"{kb('VmStk')} kB"
            vmexe  = f"{kb('VmExe')} kB"
            vmlib  = f"{kb('VmLib')} kB"
            vmswap = f"{kb('VmSwap')} kB"

            # Segmentos de /proc/<pid>/maps (en MB)
            text_mb   = a_mb(segmentos.get("text",   0))
            data_mb   = a_mb(segmentos.get("data",   0))
            heap_mb   = a_mb(segmentos.get("heap",   0))
            stack_mb  = a_mb(segmentos.get("stack",  0))
            shared_mb = a_mb(segmentos.get("shared", 0))

            minflt = f"{datos_memoria.get('min_flt', 0):,}"
            majflt = f"{datos_memoria.get('maj_flt', 0):,}"

            tabla.add_row(
                str(pid), comando,
                vmsize, vmrss, vmhwm, vmdata, vmstk, vmexe, vmlib, vmswap,
                text_mb, data_mb, heap_mb, stack_mb, shared_mb,
                minflt, majflt
            )
        
    elif vista_activa in ['3', 'f']:
        tabla = Table(title="Vista 3: File Descriptors", expand=True)

        tabla.add_column("PID",      style="cyan",    justify="right")
        tabla.add_column("Comando",  justify="left")
        tabla.add_column("Total",    style="bold",    justify="right")  # cantidad total de FDs
        tabla.add_column("Pipes",    style="yellow",  justify="right")
        tabla.add_column("Sockets",  style="magenta", justify="right")
        tabla.add_column("TTYs",     style="green",   justify="right")
        tabla.add_column("Files",    style="blue",    justify="right")
        tabla.add_column("Other",    style="dim",     justify="right")  # anon_inode, etc.
        tabla.add_column("Muestra FDs", justify="left")                 # primeros 10 FDs con destino

        resumen = snapshot_global.get("resumen", {})
        fds     = snapshot_global.get("fds", {})

        # Ordenamos por cantidad de FDs (de mayor a menor) y tomamos el Top 20
        pids_validos = [p for p in pids_activos if resumen.get(p, {}).get("comando", "").strip() != ""]
        pids_ordenados = sorted(
            pids_validos,
            key=lambda p: fds.get(p, {}).get("cantidad", 0),
            reverse=True
        )
        top_20 = pids_ordenados[:20]

        for pid in top_20:
            datos_resumen = resumen.get(pid, {})
            datos_fds     = fds.get(pid, {})

            comando = datos_resumen.get("comando", "Cargando...")
            if len(comando) > 30:
                comando = comando[:27] + "..."

            total   = str(datos_fds.get("cantidad", 0))
            pipes   = str(datos_fds.get("pipes",    0))
            sockets = str(datos_fds.get("sockets",  0))
            ttys    = str(datos_fds.get("tty",      0))
            files   = str(datos_fds.get("files",    0))
            other   = str(datos_fds.get("other",    0))

            # Construimos el texto multilínea con la muestra de FDs
            muestra = datos_fds.get("muestra", [])
            if muestra:
                lineas = [f"fd{e['fd']:>3} → {e['destino'][:40]:<40} ({e['tipo']})" for e in muestra]
                muestra_txt = "\n".join(lineas)
            else:
                muestra_txt = "(sin datos)"

            tabla.add_row(
                str(pid), comando,
                total, pipes, sockets, ttys, files, other,
                muestra_txt
            )
        
    else:
        # Un placeholder para las vistas que todavía no construimos
        tabla = Table(title=f"Vista {vista_activa} (En construcción)", expand=True)
        tabla.add_column("Aviso")
        tabla.add_row("Esta vista todavía no tiene su analizador conectado.")
        
    return tabla


def proceso_display(snapshot_global, evento_apagado):
    """Este es el PROCESO principal de la TUI que instanciás en main.py"""
    print("[TUI] Iniciando interfaz interactiva...")
    
    # 1. Arrancamos el HILO para escuchar el teclado
    hilo_teclado = threading.Thread(
        target=escuchar_teclado, 
        args=(evento_apagado,), 
        daemon=True # Daemon asegura que el hilo muera si el proceso padre muere
    )
    hilo_teclado.start()

    # 2. El bucle principal de renderizado usando el componente Live de Rich
    # Live se encarga de redibujar la tabla sin hacer "parpadear" la pantalla
    with Live(generar_tabla(snapshot_global), refresh_per_second=2) as live:
        while not evento_apagado.is_set():
            live.update(generar_tabla(snapshot_global))
            time.sleep(0.5)
            
    hilo_teclado.join()