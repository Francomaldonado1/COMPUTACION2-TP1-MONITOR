import multiprocessing
import signal
import time
import os

# Importamos nuestros analizadores
from src.analizadores.memoria import analizador_memoria
from src.analizadores.resumen import analizador_resumen
from src.analizadores.fds import analizador_fds
from src.analizadores.threads import analizador_threads

# Importamos nuestro nuevo display
from src.tui import dibujar_tui

# Simulamos el Recolector (que buscará los PIDs numéricos en /proc)
def recolector(snapshot_global, evento_apagado):
    print("[Recolector] Iniciando escaneo de /proc...")
    
    while not evento_apagado.is_set():
        try:
            pids_activos = [p for p in os.listdir('/proc') if p.isnumeric()]
            
            # Guardamos la lista en el Snapshot Global
            # Los diccionarios del Manager requieren reasignar para detectar cambios
            datos_sistema = snapshot_global["sistema"]
            datos_sistema["pids_activos"] = pids_activos
            snapshot_global["sistema"] = datos_sistema
            
        except FileNotFoundError:
            pass # Por si /proc falla momentáneamente
            
        time.sleep(2) # El recolector actualiza la lista cada 2 segundos

def iniciar_monitor():
    # 1. Levantamos el Proceso Servidor del Manager
    with multiprocessing.Manager() as manager:
        evento_apagado = manager.Event()
        
        # 2. Creamos el Snapshot Global exactamente como pide el diagrama
        snapshot_global = manager.dict({
            "resumen": manager.dict(),
            "memoria": manager.dict(),
            "fds": manager.dict(),
            "threads": manager.dict(),
            "senales": manager.dict(),
            "scheduling": manager.dict(),
            "sistema": manager.dict({"pids_activos": []}) # Acá arranca nuestro Recolector
        })

        # 3. Configuramos la señal de apagado limpio
        def mi_manejador(signum, frame):
            print("\n[Monitor] ¡SIGINT (Ctrl+C) detectado! Apagando...")
            evento_apagado.set()

        signal.signal(signal.SIGINT, mi_manejador)

        # 4. Levantamos el proceso Recolector
        p_recolector = multiprocessing.Process(
            target=recolector,
            args=(snapshot_global, evento_apagado)
        )

        p_memoria = multiprocessing.Process(
            target=analizador_memoria,
            args=(snapshot_global, evento_apagado)
        )

        p_display = multiprocessing.Process(
            target=dibujar_tui,
            args=(snapshot_global, evento_apagado)
        )

        p_resumen = multiprocessing.Process(
            target=analizador_resumen,
            args=(snapshot_global, evento_apagado)
        )

        p_fds = multiprocessing.Process(
            target=analizador_fds,
            args=(snapshot_global, evento_apagado)
        )
        
        p_threads = multiprocessing.Process(
            target=analizador_threads,
            args=(snapshot_global, evento_apagado)
        )

        # 2. Los arrancamos en paralelo
        p_recolector.start()
        p_memoria.start()
        p_display.start()
        p_resumen.start()
        p_fds.start()
        p_threads.start()

        # El padre queda mudo esperando el Ctrl+C
        while not evento_apagado.is_set():
            time.sleep(1)

        # 5. Limpieza (evitamos zombies)
        p_recolector.join()
        p_memoria.join()
        p_display.join()
        p_resumen.join()
        p_fds.join()
        p_threads.join()

        print("[Monitor] Apagado total exitoso.")