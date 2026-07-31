import os
import time
import threading
import sys
import tty
import termios
import select
from rich.live import Live
from rich.table import Table
from rich.text import Text
from rich.markup import escape
from rich.panel import Panel
from rich.console import Group

# Convierte bytes a MB con un decimal y unidad — usada en la Vista 2
def a_mb(bytes_val):
    return f"{bytes_val / (1024 * 1024):.1f} MB"

# ─── Estado global compartido del proceso TUI ────────────────────────────────
vista_activa  = '1'
modo          = 'normal'   # 'normal' | 'filtro_cmd' | 'filtro_usr' | 'ayuda'
buffer_filtro = ''         # texto que el usuario escribe en modo filtro
filtro_cmd    = ''         # filtro de comando confirmado con Enter
filtro_usr    = ''         # filtro de usuario confirmado con Enter
cursor_pos    = 0          # índice de fila seleccionada con ↑↓
pid_fijado    = None       # PID "pinneado" con Enter
_enter_press  = False      # flag: True por un frame cuando se presiona Enter
orden_vista1  = 'rss'      # 'rss' | 'cpu' | 'pid'  (cicla con c)
intervalo     = 2          # segundos entre refresco, ajustado con +/-
_lock_estado  = threading.Lock()  # protege las variables anteriores
# ─────────────────────────────────────────────────────────────────────────────

_ORDENES = ['rss', 'cpu', 'pid']  # ciclo del toggle 'c'

def escuchar_teclado(evento_apagado):
    """HILO que lee teclas sin bloquear la pantalla."""
    global vista_activa, modo, buffer_filtro, filtro_cmd, filtro_usr
    global cursor_pos, pid_fijado, _enter_press, orden_vista1, intervalo

    def leer_byte(fd, timeout=0.1):
        """Lee exactamente 1 byte con timeout. Devuelve b'' si no hay nada."""
        dr, _, _ = select.select([fd], [], [], timeout)
        if dr:
            return os.read(fd, 1)
        return b''

    try:
        with open('/dev/tty', 'r') as tty_file:
            fd = tty_file.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setcbreak(fd)
                while not evento_apagado.is_set():
                    b1 = leer_byte(fd, timeout=0.2)
                    if not b1:
                        continue

                    # Construimos la secuencia de escape byte a byte
                    if b1 == b'\x1b':
                        b2 = leer_byte(fd, timeout=0.1)
                        if b2 == b'[':
                            b3 = leer_byte(fd, timeout=0.1)
                            raw = b'\x1b[' + b3   # ej: b'\x1b[A' para flecha arriba
                        else:
                            raw = b'\x1b' + b2    # Escape solo u otra secuencia
                    else:
                        raw = b1

                    with _lock_estado:
                        if modo in ('filtro_cmd', 'filtro_usr'):
                            if raw in (b'\r', b'\n'):
                                if modo == 'filtro_cmd':
                                    filtro_cmd = buffer_filtro
                                else:
                                    filtro_usr = buffer_filtro
                                buffer_filtro = ''
                                modo = 'normal'
                            elif raw == b'\x1b':
                                buffer_filtro = ''
                                modo = 'normal'
                            elif raw in (b'\x7f', b'\x08'):
                                buffer_filtro = buffer_filtro[:-1]
                            elif len(raw) == 1 and raw[0] >= 32:
                                buffer_filtro += raw.decode('utf-8', errors='ignore')
                            continue

                        if modo == 'ayuda':
                            modo = 'normal'
                            continue

                        if raw == b'\x1b[A':
                            cursor_pos = max(0, cursor_pos - 1)
                        elif raw == b'\x1b[B':
                            cursor_pos += 1
                        elif raw in (b'\r', b'\n'):
                            _enter_press = True
                        else:
                            try:
                                tecla = raw.decode('utf-8', errors='ignore').lower()
                            except Exception:
                                continue

                            if tecla == 'q':
                                evento_apagado.set()
                            elif tecla == '/':
                                modo = 'filtro_cmd'
                                buffer_filtro = ''
                            elif tecla == 'u':
                                modo = 'filtro_usr'
                                buffer_filtro = ''
                            elif tecla in ('h', '?'):
                                modo = 'ayuda'
                            elif tecla == 'c':
                                idx = _ORDENES.index(orden_vista1)
                                orden_vista1 = _ORDENES[(idx + 1) % len(_ORDENES)]
                            elif tecla == '+':
                                intervalo = min(10, intervalo + 1)
                            elif tecla == '-':
                                intervalo = max(1, intervalo - 1)
                            elif tecla in ['1','2','3','4','5','6','7',
                                           'r','m','f','t','s','p','g']:
                                vista_activa = tecla
                                cursor_pos = 0
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except Exception:
        pass


AYUDA_TEXTO = """
  [cyan]1-7[/cyan] / [cyan]r m f t s p g[/cyan]  Cambiar de vista
  [cyan]↑ ↓[/cyan]                   Navegar por la lista de procesos
  [cyan]Enter[/cyan]                  Fijar (pin) el proceso seleccionado
  [cyan]/[/cyan]                      Filtrar por nombre de comando
  [cyan]u[/cyan]                      Filtrar por usuario
  [cyan]c[/cyan]                      Ciclar orden: RSS → CPU% → PID (Vista 1)
  [cyan]+ -[/cyan]                    Ajustar intervalo de refresco
  [cyan]q[/cyan]                      Salir
  [cyan]h / ?[/cyan]                  Esta ayuda
"""

def _pie_estado():
    """Genera la línea de estado/filtro que se muestra debajo de la tabla."""
    with _lock_estado:
        m = modo
        bf = buffer_filtro
        fc = filtro_cmd
        fu = filtro_usr
        o  = orden_vista1
        iv = intervalo
        pf = pid_fijado

    partes = []
    if fc:
        partes.append(f"[yellow]Cmd:[/yellow] [bold]{escape(fc)}[/bold]")
    if fu:
        partes.append(f"[yellow]Usr:[/yellow] [bold]{escape(fu)}[/bold]")
    if pf is not None:
        partes.append(f"[magenta]📌 PID {pf}[/magenta]")
    partes.append(f"[dim]Orden: {o.upper()} | Intervalo: {iv}s[/dim]")
    partes.append("[dim]h/?=ayuda  q=salir[/dim]")

    if m == 'filtro_cmd':
        return Text.from_markup(f"[bold green]Filtrar comando:[/bold green] {escape(bf)}█")
    elif m == 'filtro_usr':
        return Text.from_markup(f"[bold green]Filtrar usuario:[/bold green] {escape(bf)}█")
    else:
        return Text.from_markup("  ".join(partes))


def generar_tabla(snapshot_global):
    """Decide QUÉ dibujar dependiendo del modo y la vista activa."""
    global vista_activa, cursor_pos, pid_fijado, _enter_press

    def obtener_top20_y_estado(pids_ordenados):
        global cursor_pos, pid_fijado, _enter_press
        with _lock_estado:
            pf = pid_fijado
            
            # Construir la lista proyectada con TODOS los procesos (pinned al top)
            lista_proyectada = []
            if pf is not None and pf in pids_ordenados:
                lista_proyectada.append(pf)
                resto = [p for p in pids_ordenados if p != pf]
            else:
                resto = pids_ordenados
            lista_proyectada.extend(resto)
            
            # Clampear el cursor al tamaño total de la lista
            cursor_pos = min(cursor_pos, max(0, len(lista_proyectada) - 1))
            
            if _enter_press and lista_proyectada:
                nuevo_pf = lista_proyectada[cursor_pos]
                if nuevo_pf == pf:
                    pid_fijado = None  # Toggle off
                else:
                    pid_fijado = nuevo_pf
                
                _enter_press = False
                pf = pid_fijado
                
                # Reconstruir la lista si cambió el pin
                lista_proyectada = []
                if pf is not None and pf in pids_ordenados:
                    lista_proyectada.append(pf)
                    resto = [p for p in pids_ordenados if p != pf]
                else:
                    resto = pids_ordenados
                lista_proyectada.extend(resto)

            import shutil
            term_lines = shutil.get_terminal_size((80, 24)).lines
            
            # Dejamos espacio para el header, título, bordes y footer (aprox 12 a 15 líneas)
            # En la vista 7 (Global System), la tabla tiene alturas dinámicas de filas, pero
            # como usa otro sistema, no pasa nada. Para las vistas de procesos (1-6) funciona perfecto.
            limite_filas = max(5, term_lines - 14)

            # Calcular la ventana de scroll dinámica
            if cursor_pos < limite_filas:
                scroll_offset = 0
            else:
                scroll_offset = cursor_pos - (limite_filas - 1)
                
            lista_visible = lista_proyectada[scroll_offset : scroll_offset + limite_filas]
            clamped_relativo = cursor_pos - scroll_offset

            return lista_visible, clamped_relativo, pf

    with _lock_estado:
        m   = modo
        va  = vista_activa
        fc  = filtro_cmd
        fu  = filtro_usr
        c   = cursor_pos
        o   = orden_vista1

    # ── MODO AYUDA ──────────────────────────────────────────────────────────
    if m == 'ayuda':
        tabla = Table(title="Atajos de teclado", expand=True, show_lines=False)
        tabla.add_column("Ayuda", style="white")
        for linea in AYUDA_TEXTO.strip().split('\n'):
            tabla.add_row(linea)
        return Group(tabla, _pie_estado())

    # Leemos los datos base (igual que antes)
    pids_activos = snapshot_global.get("sistema", {}).get("pids_activos", [])

    if va in ['1', 'r']:
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

        resumen = snapshot_global.get("resumen", {})
        memoria = snapshot_global.get("memoria", {})
        threads = snapshot_global.get("threads", {})

        # 1. Filtrar por comando y usuario
        pids_validos = [
            p for p in pids_activos
            if resumen.get(p, {}).get("comando", "").strip() != ""
            and fc.lower() in resumen.get(p, {}).get("comando", "").lower()
            and fu.lower() in resumen.get(p, {}).get("usuario",  "").lower()
        ]

        # 2. Ordenar según la variable global 'orden_vista1'
        if o == 'rss':
            key_fn = lambda p: memoria.get(p, {}).get("VmRSS", 0)
        elif o == 'cpu':
            key_fn = lambda p: resumen.get(p, {}).get("cpu_percent", 0.0)
        else:  # pid
            key_fn = lambda p: int(p)
        pids_ordenados = sorted(pids_validos, key=key_fn, reverse=(o != 'pid'))
        # 3. Clampear cursor, actualizar pin si se presionó Enter, y obtener la lista top 20 proyectada
        top_20, clamped, pf = obtener_top20_y_estado(pids_ordenados)

        for i, pid in enumerate(top_20):
            datos_resumen = resumen.get(pid, {})
            datos_memoria = memoria.get(pid, {})
            datos_threads = threads.get(pid, {})

            ppid    = datos_resumen.get("ppid",    "?")
            usuario = datos_resumen.get("usuario",  "?")
            comando = datos_resumen.get("comando", "Cargando...")
            if len(comando) > 63:
                comando = comando[:60] + "..."
            comando = escape(comando)

            estado         = datos_resumen.get("estado", "-")
            cpu_percent    = f"{datos_resumen.get('cpu_percent', 0.0):.1f} %"
            vmrss          = f"{datos_memoria.get('VmRSS', 0):,}"
            cantidad_hilos = str(datos_threads.get("cantidad", "1"))

            # Resaltar la fila del cursor O la del PID fijado
            es_cursor = (i == clamped)
            es_pin    = (pf is not None and pid == pf)
            if es_pin:
                estilo = "on dark_green"
            elif es_cursor:
                estilo = "on dark_blue"
            else:
                estilo = ""
            es_cursor = (i == clamped)
            es_pin    = (pf is not None and pid == pf)
            if es_pin:
                estilo = "on dark_green"
            elif es_cursor:
                estilo = "on dark_blue"
            else:
                estilo = ""
            tabla.add_row(str(pid), str(ppid), str(usuario), estado, comando,
                          cpu_percent, vmrss, cantidad_hilos, style=estilo)

    elif va in ['2', 'm']:
        tabla = Table(title="Vista 2: Memoria (VmRSS, Segmentos, Page Faults)", expand=True)

        # Columnas de identidad del proceso
        tabla.add_column("PID",       style="cyan",    justify="right")
        tabla.add_column("Comando",   justify="left")

        # Columnas de consumo de RAM (de /proc/<pid>/status, en kB)
        tabla.add_column("VmSize",    style="blue",    justify="right")   # Espacio virtual total
        tabla.add_column("VmRSS",     style="magenta", justify="right")   # RAM física usada
        tabla.add_column("VmHWM",     style="red",     justify="right")   # Pico máximo de RSS
        tabla.add_column("VmData",    style="blue",    justify="right")   # Segmento de datos
        tabla.add_column("VmStk",     style="blue",    justify="right")   # Pila (stack)
        tabla.add_column("VmExe",     style="blue",    justify="right")   # Código ejecutable
        tabla.add_column("VmLib",     style="blue",    justify="right")   # Librerías compartidas
        tabla.add_column("VmSwap",    style="yellow",  justify="right")   # En swap

        # Columnas de segmentos mapeados (de /proc/<pid>/maps, convertidos a MB)
        tabla.add_column("Text(MB)",  style="green",   justify="right")   # Código ejecutable
        tabla.add_column("Data(MB)",  style="green",   justify="right")   # Datos (sin heap/stack)
        tabla.add_column("Heap(MB)",  style="green",   justify="right")   # Memoria dinámica
        tabla.add_column("Stack(MB)", style="green",   justify="right")   # Pila de llamadas
        tabla.add_column("Shr(MB)",   style="cyan",    justify="right")   # Regiones compartidas

        # Columnas de page faults (de /proc/<pid>/stat)
        tabla.add_column("MinFlt",    style="dim",     justify="right")   # Minor faults (sin I/O)
        tabla.add_column("MajFlt",    style="bold red",justify="right")   # Major faults (con I/O)

        resumen = snapshot_global.get("resumen", {})
        memoria = snapshot_global.get("memoria", {})

        # Ordenamos por VmRSS descendente y tomamos el Top 20
        pids_validos = [p for p in pids_activos if resumen.get(p, {}).get("comando", "").strip() != ""]
        pids_ordenados = sorted(
            pids_validos,
            key=lambda p: memoria.get(p, {}).get("VmRSS", 0),
            reverse=True
        )
        top_20, clamped, pf = obtener_top20_y_estado(pids_ordenados)

        for i, pid in enumerate(top_20):
            datos_resumen = resumen.get(pid, {})
            datos_memoria = memoria.get(pid, {})
            segmentos     = datos_memoria.get("segmentos", {})

            comando = datos_resumen.get("comando", "Cargando...")
            if len(comando) > 30:
                comando = comando[:27] + "..."
            comando = escape(comando)

            # Valores de /proc/<pid>/status (en kB)
            def kb(clave):
                return f"{datos_memoria.get(clave, 0):,}"

            vmsize = f"{kb('VmSize')} kB"
            vmrss  = f"{kb('VmRSS')} kB"
            vmhwm  = f"{kb('VmHWM')} kB"
            vmdata = f"{kb('VmData')} kB"
            vmstk  = f"{kb('VmStk')} kB"
            vmexe  = f"{kb('VmExe')} kB"
            vmlib  = f"{kb('VmLib')} kB"
            vmswap = f"{kb('VmSwap')} kB"

            # Segmentos de /proc/<pid>/maps (en MB)
            text_mb   = a_mb(segmentos.get("text",   0))
            data_mb   = a_mb(segmentos.get("data",   0))
            heap_mb   = a_mb(segmentos.get("heap",   0))
            stack_mb  = a_mb(segmentos.get("stack",  0))
            shared_mb = a_mb(segmentos.get("shared", 0))

            minflt = f"{datos_memoria.get('min_flt', 0):,}"
            majflt = f"{datos_memoria.get('maj_flt', 0):,}"

            es_cursor = (i == clamped)
            es_pin    = (pf is not None and pid == pf)
            if es_pin:
                estilo = "on dark_green"
            elif es_cursor:
                estilo = "on dark_blue"
            else:
                estilo = ""
            tabla.add_row(
                str(pid), comando,
                vmsize, vmrss, vmhwm, vmdata, vmstk, vmexe, vmlib, vmswap,
                text_mb, data_mb, heap_mb, stack_mb, shared_mb,
                minflt, majflt, style=estilo
            )
        
    elif va in ['3', 'f']:
        tabla = Table(title="Vista 3: File Descriptors", expand=True)

        tabla.add_column("PID",      style="cyan",    justify="right")
        tabla.add_column("Comando",  justify="left")
        tabla.add_column("Total",    style="bold",    justify="right")  # cantidad total de FDs
        tabla.add_column("Pipes",    style="yellow",  justify="right")
        tabla.add_column("Sockets",  style="magenta", justify="right")
        tabla.add_column("TTYs",     style="green",   justify="right")
        tabla.add_column("Files",    style="blue",    justify="right")
        tabla.add_column("Other",    style="dim",     justify="right")  # anon_inode, etc.
        tabla.add_column("Muestra FDs", justify="left")                 # primeros 10 FDs con destino

        resumen = snapshot_global.get("resumen", {})
        fds     = snapshot_global.get("fds", {})

        # Ordenamos por cantidad de FDs (de mayor a menor) y tomamos el Top 20
        pids_validos = [p for p in pids_activos if resumen.get(p, {}).get("comando", "").strip() != ""]
        pids_ordenados = sorted(
            pids_validos,
            key=lambda p: fds.get(p, {}).get("cantidad", 0),
            reverse=True
        )
        top_20, clamped, pf = obtener_top20_y_estado(pids_ordenados)

        for i, pid in enumerate(top_20):
            datos_resumen = resumen.get(pid, {})
            datos_fds     = fds.get(pid, {})

            comando = datos_resumen.get("comando", "Cargando...")
            if len(comando) > 30:
                comando = comando[:27] + "..."
            comando = escape(comando)

            total   = str(datos_fds.get("cantidad", 0))
            pipes   = str(datos_fds.get("pipes",    0))
            sockets = str(datos_fds.get("sockets",  0))
            ttys    = str(datos_fds.get("tty",      0))
            files   = str(datos_fds.get("files",    0))
            other   = str(datos_fds.get("other",    0))

            # Construimos el texto multilínea con la muestra de FDs
            muestra = datos_fds.get("muestra", [])
            if muestra:
                lineas = [f"fd{e['fd']:>3} → {e['destino'][:40]:<40} ({e['tipo']})" for e in muestra]
                muestra_txt = "\n".join(lineas)
            else:
                muestra_txt = "(sin datos)"

            es_cursor = (i == clamped)
            es_pin    = (pf is not None and pid == pf)
            if es_pin:
                estilo = "on dark_green"
            elif es_cursor:
                estilo = "on dark_blue"
            else:
                estilo = ""
            tabla.add_row(
                str(pid), comando,
                total, pipes, sockets, ttys, files, other,
                muestra_txt, style=estilo
            )
        
    elif va in ['4', 't']:
        tabla = Table(title="Vista 4: Threads", expand=True)

        tabla.add_column("PID",      style="cyan",    justify="right")
        tabla.add_column("Comando",  justify="left")
        tabla.add_column("Hilos",    style="bold",    justify="right")  # cantidad total
        tabla.add_column("Detalle de Hilos", justify="left")            # primeros 10 con info

        resumen = snapshot_global.get("resumen",  {})
        threads = snapshot_global.get("threads",  {})

        # Ordenamos por cantidad de hilos (de mayor a menor) y tomamos el Top 20
        pids_validos = [p for p in pids_activos if resumen.get(p, {}).get("comando", "").strip() != ""]
        pids_ordenados = sorted(
            pids_validos,
            key=lambda p: threads.get(p, {}).get("cantidad", 0),
            reverse=True
        )
        top_20, clamped, pf = obtener_top20_y_estado(pids_ordenados)

        for i, pid in enumerate(top_20):
            datos_resumen = resumen.get(pid, {})
            datos_threads = threads.get(pid, {})

            comando = datos_resumen.get("comando", "Cargando...")
            if len(comando) > 30:
                comando = comando[:27] + "..."
            comando = escape(comando)

            cantidad = str(datos_threads.get("cantidad", 0))

            # Construimos el detalle multilínea con la muestra de hilos
            hilos_lista = datos_threads.get("hilos", [])
            if hilos_lista:
                lineas = [
                    f"tid{h['tid']:>6}  {h['nombre']:<16}  {h['estado']}  "
                    f"CPU:{h['cpu_pct']:>5.1f}%  cs:{h['vol_cs']:,}v/{h['invol_cs']:,}i"
                    for h in hilos_lista
                ]
                detalle_txt = "\n".join(lineas)
            else:
                detalle_txt = "(sin datos)"

            es_cursor = (i == clamped)
            es_pin    = (pf is not None and pid == pf)
            if es_pin:
                estilo = "on dark_green"
            elif es_cursor:
                estilo = "on dark_blue"
            else:
                estilo = ""
            tabla.add_row(str(pid), comando, cantidad, detalle_txt, style=estilo)

    elif va in ['5', 's']:
        tabla = Table(title="Vista 5: Señales", expand=True)

        tabla.add_column("PID",      style="cyan",    justify="right")
        tabla.add_column("Comando",  justify="left")
        tabla.add_column("Bloqueadas (SigBlk)", style="yellow")
        tabla.add_column("Ignoradas (SigIgn)",  style="dim")
        tabla.add_column("Atrapadas (SigCgt)",  style="green")
        tabla.add_column("Pdte. Proc (SigPnd)", style="red")
        tabla.add_column("Pdte. Grp (ShdPnd)",  style="red")

        resumen = snapshot_global.get("resumen", {})
        senales = snapshot_global.get("senales", {})

        # Para señales, ordenamos por la cantidad de señales bloqueadas/atrapadas
        # para ver los procesos más "interesantes" en lugar de solo los primeros PIDs
        pids_validos = [p for p in pids_activos if resumen.get(p, {}).get("comando", "").strip() != ""]
        pids_ordenados = sorted(
            pids_validos,
            key=lambda p: len(senales.get(p, {}).get("SigBlk", "")) + len(senales.get(p, {}).get("SigCgt", "")),
            reverse=True
        )
        top_20, clamped, pf = obtener_top20_y_estado(pids_ordenados)

        for i, pid in enumerate(top_20):
            datos_resumen = resumen.get(pid, {})
            datos_senales = senales.get(pid, {})

            comando = datos_resumen.get("comando", "Cargando...")
            if len(comando) > 30:
                comando = comando[:27] + "..."
            comando = escape(comando)

            sig_blk = datos_senales.get("SigBlk", "-")
            sig_ign = datos_senales.get("SigIgn", "-")
            sig_cgt = datos_senales.get("SigCgt", "-")
            sig_pnd = datos_senales.get("SigPnd", "-")
            shd_pnd = datos_senales.get("ShdPnd", "-")

            es_cursor = (i == clamped)
            es_pin    = (pf is not None and pid == pf)
            if es_pin:
                estilo = "on dark_green"
            elif es_cursor:
                estilo = "on dark_blue"
            else:
                estilo = ""
            tabla.add_row(
                str(pid), comando,
                sig_blk, sig_ign, sig_cgt, sig_pnd, shd_pnd, style=estilo
            )

    elif va in ['6', 'p']:
        tabla = Table(title="Vista 6: Scheduling", expand=True)

        tabla.add_column("PID",      style="cyan",    justify="right")
        tabla.add_column("Comando",  justify="left")
        tabla.add_column("Política", style="magenta")
        tabla.add_column("Prio / Nice / RT", style="yellow")
        tabla.add_column("CPU Affinity", style="green")
        tabla.add_column("Ctx Swtch (v/iv)", style="blue")
        tabla.add_column("Time (U/S seg)", style="dim")
        tabla.add_column("SID / PGID", style="bold")

        resumen = snapshot_global.get("resumen", {})
        sched = snapshot_global.get("scheduling", {})

        # Ordenamos primero por prioridad interna (menor número = mayor prioridad)
        # y desempatamos por la cantidad de context switches (los más activos)
        pids_validos = [p for p in pids_activos if resumen.get(p, {}).get("comando", "").strip() != ""]
        pids_ordenados = sorted(
            pids_validos,
            key=lambda p: (
                int(sched.get(p, {}).get("prioridad", 20)),
                -int(sched.get(p, {}).get("vol_cs", 0))
            )
        )
        top_20, clamped, pf = obtener_top20_y_estado(pids_ordenados)

        for i, pid in enumerate(top_20):
            datos_resumen = resumen.get(pid, {})
            datos_sched = sched.get(pid, {})

            comando = datos_resumen.get("comando", "Cargando...")
            if len(comando) > 20:
                comando = comando[:17] + "..."
            comando = escape(comando)

            politica = datos_sched.get("politica", "-")
            prio = datos_sched.get("prioridad", "-")
            nice = datos_sched.get("nice", "-")
            rt_prio = datos_sched.get("rt_prio", "-")
            affinity = datos_sched.get("affinity", "-")
            vol_cs = datos_sched.get("vol_cs", "0")
            invol_cs = datos_sched.get("invol_cs", "0")
            utime = str(datos_sched.get("utime", "0"))
            stime = str(datos_sched.get("stime", "0"))
            sid = str(datos_sched.get("sid", "-"))
            pgid = str(datos_sched.get("pgid", "-"))

            # Formateos agrupados
            prio_str = f"{prio} / {nice} / {rt_prio}"
            cs_str = f"{vol_cs} / {invol_cs}"
            time_str = f"{utime} / {stime}"
            sid_pgid_str = f"{sid} / {pgid}"

            es_cursor = (i == clamped)
            es_pin    = (pf is not None and pid == pf)
            if es_pin:
                estilo = "on dark_green"
            elif es_cursor:
                estilo = "on dark_blue"
            else:
                estilo = ""
            tabla.add_row(
                str(pid), comando,
                politica, prio_str, affinity,
                cs_str, time_str, sid_pgid_str, style=estilo
            )

    elif va in ['7', 'g']:
        tabla = Table(title="Vista 7: Stats Globales del Sistema", expand=True, show_lines=True)

        tabla.add_column("Categoría", style="cyan", justify="right", ratio=1)
        tabla.add_column("Métricas", style="green", ratio=3)

        sys_stats = snapshot_global.get("sistema_global", {})
        resumen = snapshot_global.get("resumen", {})
        memoria_snap = snapshot_global.get("memoria", {})

        # CPU
        cpu_str = (f"User: {sys_stats.get('cpu_user', 0.0)}% | "
                   f"System: {sys_stats.get('cpu_system', 0.0)}% | "
                   f"Idle: {sys_stats.get('cpu_idle', 0.0)}% | "
                   f"IOWait: {sys_stats.get('cpu_iowait', 0.0)}%")
        tabla.add_row("CPU Global", cpu_str)

        # Load Average
        tabla.add_row("Load Average (1, 5, 15 min)", sys_stats.get("loadavg", "-"))

        # Memoria
        mem = sys_stats.get("meminfo", {})
        mem_str = (f"Total: {a_mb(mem.get('MemTotal',0)*1024)} | "
                   f"Libre: {a_mb(mem.get('MemFree',0)*1024)} | "
                   f"Buffers: {a_mb(mem.get('Buffers',0)*1024)}\n"
                   f"Cached: {a_mb(mem.get('Cached',0)*1024)} | "
                   f"Swap Total: {a_mb(mem.get('SwapTotal',0)*1024)} | "
                   f"Swap Libre: {a_mb(mem.get('SwapFree',0)*1024)}")
        tabla.add_row("Memoria", mem_str)

        # Tiempos
        import datetime
        uptime_segs = sys_stats.get("uptime", 0)
        uptime_str = str(datetime.timedelta(seconds=int(uptime_segs)))

        btime_segs = sys_stats.get("btime", 0)
        btime_str = datetime.datetime.fromtimestamp(btime_segs).strftime("%Y-%m-%d %H:%M:%S") if btime_segs else "-"

        tabla.add_row("Tiempos", f"Uptime: {uptime_str} | Boot Time: {btime_str}")

        # Estados
        est = sys_stats.get("estados", {})
        est_str = (f"Total: {est.get('total', 0)} | Running (R): {est.get('R', 0)} | "
                   f"Sleeping (S): {est.get('S', 0)} | Zombies (Z): {est.get('Z', 0)}\n"
                   f"Threads Totales: {est.get('threads', 0)}")
        tabla.add_row("Procesos y Threads", est_str)

        # Top 3 (calculados al vuelo por la TUI usando los datos que ya existen)
        pids_validos = [p for p in pids_activos if resumen.get(p, {}).get("comando", "").strip() != ""]

        top_cpu = sorted(pids_validos, key=lambda p: resumen.get(p, {}).get("cpu_percent", 0.0), reverse=True)[:3]
        top_cpu_str = "\n".join([f"{i+1}. PID {p} ({escape(resumen.get(p,{}).get('comando',''))[:20]}...) - {resumen.get(p,{}).get('cpu_percent', 0)}%" for i, p in enumerate(top_cpu)])
        
        top_mem = sorted(pids_validos, key=lambda p: memoria_snap.get(p, {}).get("VmRSS", 0), reverse=True)[:3]
        top_mem_str = "\n".join([f"{i+1}. PID {p} ({escape(resumen.get(p,{}).get('comando',''))[:20]}...) - {a_mb(memoria_snap.get(p,{}).get('VmRSS', 0) * 1024)}" for i, p in enumerate(top_mem)])

        tabla.add_row("Top 3 Procesos (CPU)", top_cpu_str if top_cpu_str else "-")
        tabla.add_row("Top 3 Procesos (Memoria)", top_mem_str if top_mem_str else "-")

    else:
        # Un placeholder para las vistas que todavía no construimos
        tabla = Table(title=f"Vista {vista_activa} (En construcción)", expand=True)
        tabla.add_column("Aviso")
        tabla.add_row("Esta vista todavía no tiene su analizador conectado.")

    return Group(tabla, _pie_estado())


def proceso_display(snapshot_global, evento_apagado):
    """Proceso principal de la TUI."""
    print("[TUI] Iniciando interfaz interactiva...")

    try:
        hilo_teclado = threading.Thread(
            target=escuchar_teclado,
            args=(evento_apagado,),
            daemon=True
        )
        hilo_teclado.start()

        with Live(generar_tabla(snapshot_global), refresh_per_second=4) as live:
            while not evento_apagado.is_set():
                live.update(generar_tabla(snapshot_global))
                with _lock_estado:
                    iv = intervalo
                for _ in range(max(1, iv * 4)):
                    if evento_apagado.is_set():
                        break
                    time.sleep(0.25)

        hilo_teclado.join()

    finally:
        import subprocess
        try:
            subprocess.run(["stty", "sane"], check=False)
        except Exception:
            pass
