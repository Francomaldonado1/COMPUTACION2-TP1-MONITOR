import time

def dibujar_interfaz(memoria_compartida, mi_lock, evento_apagado):
    print("[TUI] Iniciando interfaz...")
    
    while not evento_apagado.is_set():
        # Leemos de forma segura
        with mi_lock:
            valor_actual = memoria_compartida.value
            
        print(f" -> Consumo actual de memoria: {valor_actual} kB")
        time.sleep(2)
        
    print("[TUI] Bandera detectada. Apagando pantalla.")