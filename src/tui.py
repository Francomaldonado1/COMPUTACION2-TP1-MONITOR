import time
import threading
import sys
import tty
import termios
import select
from rich.live import Live
from rich.table import Table

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
        tabla = Table(title="Vista 2: Memoria", expand=True)
        
    elif vista_activa in ['3', 'f']:
        tabla = Table(title="Vista 3: File Descriptors", expand=True)
        # Acá definís tus columnas de FDs y llenás el for...
        
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