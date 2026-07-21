import time
import threading
import sys
import tty
import termios
from rich.live import Live
from rich.table import Table

# Nuestra variable global compartida en la memoria del proceso
vista_activa = '1'

def escuchar_teclado(evento_apagado):
    """Este HILO corre en segundo plano escuchando el teclado sin bloquear la pantalla"""
    global vista_activa
    
    # Configuración mágica de Linux para leer teclas de a una sin apretar Enter
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    
    try:
        tty.setcbreak(sys.stdin.fileno())
        while not evento_apagado.is_set():
            tecla = sys.stdin.read(1).lower() # Leemos 1 caracter y lo pasamos a minúscula
            
            # Teclas de las vistas obligatorias
            if tecla in ['1', '2', '3', '4', '5', '6', '7', 'r', 'm', 'f', 't', 's', 'p', 'g']:
                vista_activa = tecla
                
            # Tecla para salir limpiamente
            elif tecla == 'q':
                evento_apagado.set()
                
    finally:
        # Es vital restaurar la terminal a su estado normal al salir, o se rompe la consola
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def generar_tabla(snapshot_global):
    """Esta función decide QUÉ dibujar dependiendo de la vista activa"""
    global vista_activa
    
    # Leemos los datos base (igual que antes)
    pids_activos = snapshot_global.get("sistema", {}).get("pids_activos", [])
    
    if vista_activa in ['1', 'r']:
        tabla = Table(title="Vista 1: Resumen (Estado, CPU, RSS, Threads)", expand=True)
        # Acá definís tus columnas de Resumen y llenás el for...
        
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