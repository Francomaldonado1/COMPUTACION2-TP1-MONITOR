import multiprocessing
import signal
import time
import os

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
        
        p_recolector.start()
        
        # (Para probar, imprimimos el estado del diccionario desde el padre)
        while not evento_apagado.is_set():
            pids = snapshot_global["sistema"].get("pids_activos", [])
            print(f"[Main] Snapshot actualizado. Total procesos vivos: {len(pids)}")
            time.sleep(3)

        # 5. Limpieza (evitamos zombies)
        p_recolector.join()
        print("[Monitor] Apagado total exitoso.")