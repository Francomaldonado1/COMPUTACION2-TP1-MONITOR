import time

def recolectar_datos(pid, memoria_compartida, mi_lock, evento_apagado):
    ruta = f"/proc/{pid}/status"
    
    print(f"[Reader] Iniciando lectura del PID {pid}...")
    
    # El bucle corta si el padre levanta la bandera
    while not evento_apagado.is_set():
        try:
            with open(ruta, 'r') as f:
                for linea in f:
                    if "VmSize:" in linea:
                        partes = linea.split()
                        memoria_entera = int(partes[1])
                        
                        # Guardamos de forma segura
                        with mi_lock:
                            memoria_compartida.value = memoria_entera
                        break  # Encontramos el dato, dejamos de leer por esta vuelta
                        
        except FileNotFoundError:
            print(f"\n[Reader] Error: El proceso {pid} no existe o ya murió.")
            evento_apagado.set() # Avisamos a los demás que hay que apagar todo
            
        time.sleep(2) # Hacemos una pausa antes de volver a leer
        
    print("[Reader] Bandera detectada. Cerrando limpiamente.")