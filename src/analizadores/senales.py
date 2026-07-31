import os
import time
import signal

# Precomputamos el mapa de señales para decodificar rápido. Ej: 9 -> "SIGKILL"
MAPA_SENALES = {sig.value: sig.name for sig in signal.Signals}

def decodificar_mascara(mascara_hex):
    """
    Convierte una máscara hexadecimal (ej: '0000000000000002') a string de nombres.
    El bit N (0-indexado) representa la señal N+1.
    """
    try:
        mascara = int(mascara_hex, 16)
    except ValueError:
        return ""
        
    nombres = []
    rt_count = 0
    # Recorremos hasta 64 bits (señales estándar y de tiempo real en Linux)
    for sig_num in range(1, 65):
        if mascara & (1 << (sig_num - 1)):
            if sig_num < 32:
                # Señal estándar
                nombre = MAPA_SENALES.get(sig_num, f"SIG_{sig_num}")
                nombres.append(nombre)
            else:
                # Señal de tiempo real (Real-Time signal)
                rt_count += 1
            
    resultado = ", ".join(nombres)
    
    if rt_count > 0:
        if resultado:
            resultado += f"\n(+ {rt_count} de tiempo real)"
        else:
            resultado = f"{rt_count} de tiempo real"
            
    return resultado if resultado else "-"

def analizador_senales(snapshot_global, evento_apagado, intervalo_val):
    print("[Señales] Analizador iniciado...")

    while not evento_apagado.is_set():
        pids = snapshot_global["sistema"].get("pids_activos", [])
        senales_local = {}
        
        for pid in pids:
            try:
                sig_blk = sig_ign = sig_cgt = sig_pnd = shd_pnd = "0000000000000000"
                
                with open(f"/proc/{pid}/status", "r") as f:
                    for linea in f:
                        if linea.startswith("SigBlk:"):
                            sig_blk = linea.split()[1]
                        elif linea.startswith("SigIgn:"):
                            sig_ign = linea.split()[1]
                        elif linea.startswith("SigCgt:"):
                            sig_cgt = linea.split()[1]
                        elif linea.startswith("SigPnd:"):
                            sig_pnd = linea.split()[1]
                        elif linea.startswith("ShdPnd:"):
                            shd_pnd = linea.split()[1]

                senales_local[pid] = {
                    "SigBlk": decodificar_mascara(sig_blk),
                    "SigIgn": decodificar_mascara(sig_ign),
                    "SigCgt": decodificar_mascara(sig_cgt),
                    "SigPnd": decodificar_mascara(sig_pnd),
                    "ShdPnd": decodificar_mascara(shd_pnd),
                }
                
            except (FileNotFoundError, PermissionError):
                continue
                
        snapshot_global["senales"] = senales_local
        time.sleep(intervalo_val.value)
