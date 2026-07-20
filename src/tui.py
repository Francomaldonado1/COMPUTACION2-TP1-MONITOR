import time
from rich.live import Live
from rich.table import Table

def dibujar_tui(snapshot_global, evento_apagado):
    
    # Esta función arma el "cuadro" que vamos a dibujar
    def generar_tabla():
        # 1. Configuramos las columnas de la tabla
        tabla = Table(title="Monitor de Memoria (Top 15 procesos)", expand=True)
        tabla.add_column("PID", justify="right", style="cyan", no_wrap=True)
        tabla.add_column("Comando", justify="left", style="blue")
        tabla.add_column("VmSize (Total)", justify="right", style="magenta")
        tabla.add_column("VmRSS (Física)", justify="right", style="green")
        tabla.add_column("Page Faults (Min/Maj)", justify="right", style="yellow")
        tabla.add_column("FDs", justify="right", style="cyan")
        tabla.add_column("Threads", justify="right", style='blue') 
        tabla.add_column("Estado", justify="right", style='green')
        tabla.add_column("CPU (%)", justify="right", style='red')

        # 2. Leemos del Snapshot Global
        memoria = snapshot_global.get("memoria", {})
        resumen = snapshot_global.get("resumen", {})
        fds = snapshot_global.get("fds", {})
        threads = snapshot_global.get("threads", {})
        cpu_estado = snapshot_global.get("cpu_estado", {})


        # 3. ORDENAMIENTO (Crucial para no saturar la pantalla)
        # Ordenamos los PIDs según quién consume más VmRSS y agarramos solo los primeros 15
        pids_ordenados = sorted(
            memoria.keys(), 
            key=lambda k: memoria[k].get("VmRSS", 0), 
            reverse=True
        )[:15]

        # 4. Llenamos las filas de la tabla
        for pid in pids_ordenados:
            datos = memoria[pid]
            # Formateamos los números con comas para que sean legibles (ej: 145,000)
            vmsize = f"{datos.get('VmSize', 0):,} kB"
            vmrss = f"{datos.get('VmRSS', 0):,} kB"
            faults = f"{datos.get('min_flt', 0)} / {datos.get('maj_flt', 0)}"

            # 5. Leemos el comando del analizador de resumen
            # Si el analizador de resumen todavía no lo procesó, mostramos "Cargando..."
            datos_resumen = resumen.get(pid, {})
            comando = datos_resumen.get("comando", "Cargando...")

            # RECORTAMOS VISUALMENTE: Si el comando es gigante, lo cortamos y le ponemos "..."
            if len(comando) > 45:
                comando = comando[:42] + "..."

            datos_fds = fds.get(pid, {})
            cantidad_fds = str(datos_fds.get("cantidad", "-")) # Guion si no tenemos permiso

            datos_threads = threads.get(pid, {})
            cantidad_threads = str(datos_threads.get("cantidad", "1"))
    
            datos_cpu = cpu_estado.get(pid, {})
            estado = datos_cpu.get("estado", "-")
            cpu_percent = f"{datos_cpu.get("cpu_percent", 0.0)}%"

            tabla.add_row(pid, comando, vmsize, vmrss, faults, cantidad_fds, cantidad_threads, estado, cpu_percent)

        return tabla

    # Arrancamos el dibujado en vivo (refresca 2 veces por segundo)
    with Live(generar_tabla(), refresh_per_second=2, transient=True) as live:
        while not evento_apagado.is_set():
            # En cada vuelta del bucle, le pedimos que actualice el dibujo con datos nuevos
            live.update(generar_tabla())
            time.sleep(0.5)