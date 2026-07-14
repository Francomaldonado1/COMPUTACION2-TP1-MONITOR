import os
from src.monitor import iniciar_monitor

if __name__ == "__main__":
    mi_pid = os.getpid()
    print(f"--- INICIANDO TP MONITOR ---")
    print(f"Monitoreando el PID: {mi_pid}")
    
    # Arrancamos la orquesta
    iniciar_monitor(mi_pid)