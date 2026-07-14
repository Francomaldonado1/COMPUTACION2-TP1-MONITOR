import multiprocessing
import signal
import sys
from src.reader import recolectar_datos
from src.tui import dibujar_interfaz

def iniciar_monitor(pid):
    # 1. Creamos las herramientas IPC (Memoria, Candado, Evento)
    # 'i' significa integer (entero) y 0 es el valor inicial
    memoria_compartida = multiprocessing.Value('i', 0) 
    mi_lock = multiprocessing.Lock()
    evento_apagado = multiprocessing.Event()

    # 2. Configuramos el manejador de la señal Ctrl+C
    def mi_manejador(signum, frame):
        print("\n[Monitor] ¡SIGINT (Ctrl+C) detectado! Levantando bandera de apagado...")
        evento_apagado.set()

    signal.signal(signal.SIGINT, mi_manejador)

    # 3. Preparamos los procesos (pasando los argumentos como tuplas)
    p_reader = multiprocessing.Process(
        target=recolectar_datos,
        args=(pid, memoria_compartida, mi_lock, evento_apagado)
    )
    
    p_tui = multiprocessing.Process(
        target=dibujar_interfaz,
        args=(memoria_compartida, mi_lock, evento_apagado)
    )

    # 4. Los hacemos nacer
    p_reader.start()
    p_tui.start()

    # 5. El padre se queda bloqueado acá hasta que los hijos terminen
    p_reader.join()
    p_tui.join()
    
    print("[Monitor] Todos los procesos limpios. Apagado total exitoso.")