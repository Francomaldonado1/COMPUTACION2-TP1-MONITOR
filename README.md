# Monitor de Procesos — TP1 Computación II

**Universidad de Mendoza | Ingeniería Informática**

---

## Descripción general

Monitor de procesos en tiempo real para Linux, similar a `htop`, que muestra la anatomía interna de cada proceso: estado, memoria, file descriptors, threads, señales y scheduling. Toda la información se extrae directamente de `/proc` sin usar `psutil` ni herramientas externas.

El sistema es multiproceso: un recolector central lista los PIDs activos, 7 analizadores especializados corren en paralelo extrayendo distintas dimensiones de cada proceso, y un proceso de display renderiza la TUI en tiempo real.

**Uso:**
```bash
docker compose up --build
# o en desarrollo local:
python3 app.py
```

**Keybindings:**
| Tecla | Acción |
|---|---|
| `1-7` / `r m f t s p g` | Cambiar vista |
| `↑ ↓` | Navegar lista de procesos |
| `q` | Salir limpiamente |

---

## Diagrama de arquitectura

```
       ┌──────────────────────────────────────┐
       │         SNAPSHOT GLOBAL              │
       │     (Manager dict compartido)        │
       │  resumen / memoria / fds / threads   │
       │  senales / scheduling / sistema      │
       └────────▲──────────────────▲──────────┘
                │ escriben          │ lee
   ┌────────────┼──────┬────────────┘
   │            │      │
┌──▼──────┐ ┌──▼───┐  ...  ┌──────────┐
│Resumen  │ │Mem.  │       │ Display  │
│(2s)     │ │(3s)  │       │ TUI      │
└─────────┘ └──────┘       └──────────┘
   7 analizadores en paralelo, cada uno con su intervalo
```

---

## Decisiones de diseño

### ¿Por qué `Manager.dict` y no un `dict` normal?

Cuando se hace `fork()` para crear un proceso hijo, Python aplica Copy-on-Write (COW): el hijo obtiene una copia del espacio de memoria del padre. Cualquier modificación en el hijo **no se propaga al padre ni a otros hijos** — cada proceso tiene su propia copia aislada.

`multiprocessing.Manager` crea un proceso servidor separado que aloja el diccionario real. Los demás procesos acceden a él mediante proxies que hacen llamadas IPC bajo el capó. Esto garantiza que todos los analizadores y el display lean y escriban el mismo diccionario compartido.

### ¿Por qué RSS aparece en la Vista 1 (Resumen)?

La consigna presenta una leve inconsistencia: la tabla de "Datos básicos (vista Resumen)" no lista RSS explícitamente, pero la tabla de vistas obligatorias sí incluye RSS en la descripción de Vista 1: *"Resumen (estado, CPU, **RSS**, threads, comando)"*.

**Decisión tomada:** mantener RSS en Vista 1. En monitores como `htop` y `top`, tener la memoria RSS visible en la lista principal es estándar porque permite evaluar el impacto de un proceso de un vistazo, sin cambiar de vista. La Vista 2 (Memoria) complementa esto con el desglose completo (VmSize, VmData, VmStk, VmHWM, VmSwap, page faults).

### ¿Por qué no existe `analizador_cpu.py` separado?

Los 7 analizadores definidos en la consigna son: resumen, memoria, FDs, threads, señales, scheduling y sistema. No existe un "analizador de CPU" independiente. El cálculo de CPU% (delta de jiffies entre ciclos) y el campo Estado son parte de los **datos básicos del resumen** y por lo tanto responsabilidad de `analizador_resumen.py`.

### ¿Por qué la Vista 2 (Memoria) tiene una tabla muy ancha?

La consigna requiere mostrar 8 campos de `/proc/<pid>/status` (VmSize, VmRSS, VmData, VmStk, VmExe, VmLib, VmHWM, VmSwap), 5 segmentos de `/proc/<pid>/maps` (text, data, heap, stack, shared) y 2 contadores de page faults — 17 columnas en total.

Opciones evaluadas:
1. **Tabla única ancha** — muestra todo junto, requiere scroll horizontal en terminales angostas
2. **Dos tablas separadas** — rompe la lectura lineal; `rich` no admite scroll horizontal nativo entre tablas
3. **Selección de columnas** — sacrifica la completitud exigida por la consigna

**Decisión tomada:** tabla única ancha (opción 1). Prioriza mostrar todos los datos requeridos por la consigna sobre la comodidad en terminales pequeñas. En terminal maximizada es completamente legible. Una versión futura podría implementar paginado de columnas con teclas de navegación horizontal.

### ¿Por qué Vista 2 incluye PID y Comando si la consigna no los lista?

La consigna describe los *datos de memoria* a extraer, no el layout completo de la tabla. Sin una columna de identificación, la tabla pierde todo contexto: los valores de VmRSS o page faults son inútiles si no sabés a qué proceso pertenecen.

**Decisión tomada:** se mantienen PID y Comando (truncado a 30 chars) como columnas de identidad. PID es imprescindible como clave de referencia; Comando hace la tabla legible para un humano. Esta es la práctica estándar en herramientas como `top`, `htop` y `ps`.

### ¿Por qué `shared` se clasifica primero en el parseo de `/proc/<pid>/maps`?

En `leer_segmentos_maps()`, el `if/elif` evalúa condiciones en orden y entra solo en la primera que sea verdadera. El orden importa cuando una región podría satisfacer más de una condición simultáneamente.

Ejemplo teórico: una región con permisos `rw-s` y etiqueta `[heap]` satisfaría tanto "shared" (perms[3] == 's') como "heap" (etiqueta == '[heap]'). Si chequeáramos `[heap]` primero, esa región quedaría mal clasificada como heap en lugar de como shared.

**Decisión tomada:** chequear `shared` primero garantiza que cualquier región marcada como compartida (`s`) se clasifique como tal, independientemente de su etiqueta. Las regiones privadas (`p`) nunca entran en ese branch, así que el resto de la lógica opera sin ambigüedad.

---

### ¿Por qué Vista 3 muestra solo una muestra de 10 FDs por proceso?

La consigna requiere mostrar el destino de cada FD abierto. El problema es que un proceso moderno puede tener cientos de FDs (Brave o Antigravity tienen entre 50 y 200+). Mostrar todos en una tabla en tiempo real haría que cada fila del proceso tuviera cientos de líneas — la tabla sería inutilizable.

**Decisión tomada:** almacenamos y mostramos los primeros **10 FDs ordenados numéricamente** (`sorted(key=int)`) como muestra representativa. Esto garantiza que stdin (fd 0), stdout (fd 1) y stderr (fd 2) siempre aparezcan, dando contexto inmediato sobre cómo está conectado el proceso (¿a una terminal? ¿a un pipe? ¿a /dev/null?). Los contadores por tipo (Pipes, Sockets, TTYs, Files, Other) muestran el total real sin limitación.

Esta solución cumple el espíritu de la consigna — mostrar destinos reales de FDs — sin sacrificar la usabilidad de la TUI.

---

### ¿Por qué Vista 4 muestra solo 10 hilos por proceso?

Por el mismo motivo que la muestra de FDs: procesos como navegadores o servidores pueden tener decenas o cientos de hilos. Mostrar todos haría la tabla ilegible en tiempo real.

**Decisión tomada:** se almacenan y muestran los primeros **10 hilos ordenados por TID** (el hilo principal siempre tiene el TID == PID y aparece primero). La columna "Hilos" muestra el total real. El detalle multilínea incluye TID, nombre (`comm`), estado, CPU% y context switches voluntarios/involuntarios.

---

### ¿Por qué Vista 5 (Señales) agrupa las señales de tiempo real?

Al decodificar las máscaras de señales de `/proc/<pid>/status`, muchos procesos del sistema y aplicaciones multihilo (como `init` o los que usan glibc/NPTL) bloquean o atrapan una gran cantidad de señales de tiempo real (desde la 32 a la 64). Mostrar los nombres de todas estas señales individualmente provocaba que cada fila ocupara demasiado espacio vertical, arruinando la legibilidad de la tabla.

**Decisión tomada:** el analizador decodifica y muestra por nombre las **señales estándar (1 a 31)**, que son las más útiles para el monitoreo general. Si el proceso tiene señales de tiempo real activas, se agrupan en un resumen corto al final (ej: `(+ 33 de tiempo real)`). Esto mantiene la fidelidad de la información sin romper la interfaz gráfica.

---

### Criterios de ordenamiento (Top 20) en Vistas 5 y 6

Para que la interfaz gráfica sea verdaderamente útil como herramienta de monitoreo, no alcanza con listar los primeros 20 PIDs numéricamente (lo que suele mostrar puros hilos pasivos del kernel). Decidimos implementar un filtrado inteligente en la TUI:

- **Vista 5 (Señales):** Ordena descendentemente según la cantidad de señales bloqueadas (`SigBlk`) y atrapadas (`SigCgt`). Esto saca a la luz los procesos de usuario más complejos (ej: navegadores, entornos de escritorio) que configuran su propio manejo de señales.
- **Vista 6 (Scheduling):** Ordena primero por **prioridad absoluta del kernel** (donde los valores menores como `-100` ganan), y desempata por la cantidad de **context switches voluntarios**. Así, los primeros procesos en pantalla son siempre los más críticos del sistema (procesos RT) ordenados por qué tan activos están en ese preciso instante.

---

### Persistencia de Procesos (Pinning) en la TUI

Se diseñó un mecanismo de "pinning" usando la tecla `Enter` que guarda globalmente el PID seleccionado en memoria. La función renderizadora `obtener_top20_y_estado` fue diseñada para inyectar este PID siempre en el tope (posición 0) de la lista *antes* de renderizar. De esta forma, el proceso fijado no solo se marca de color verde, sino que su posición sobrevive a los cambios de vista, filtros, e intervalos de actualización sin perder el foco.

### Scroll Dinámico e Infinito

En lugar de limitar la tabla estrictamente a 20 procesos, el sistema calcula matemáticamente la cantidad de líneas disponibles en el momento exacto usando `shutil.get_terminal_size().lines`. A partir de ese límite dinámico, la lista se segmenta (`lista[offset:offset+limite]`) a medida que el cursor baja. Esto evita que `Rich` trunque la tabla rompiendo el renderizado inferior y permite explorar todos los procesos del sistema, maximizando la usabilidad sin importar cuán pequeña sea la ventana del usuario.

---

### Señales: Patrón Self-Pipe para Async-Signal-Safety

Los handlers de señal en Linux tienen restricciones muy severas: no pueden hacer I/O bloqueante, no pueden pedir memoria, no pueden bloquear. Si llamamos a `print()`, `json.dump()` o cualquier función de `rich` desde un handler, corremos el riesgo de un deadlock si la señal interrumpe al programa justo en medio de otra operación similar.

Para resolverlo implementamos el **patrón self-pipe**: el handler solo ejecuta `os.write(pipe, bytes([signum]))`, que es una llamada al sistema atómica y 100% async-signal-safe. Un hilo separado (`loop_senales`) lee ese byte del pipe y ejecuta la acción real (recargar config, dumpear JSON, etc.) sin ninguna restricción. Este patrón fue visto en clase 6.

### Señales: Timeout de `select()` para Shutdown Limpio

El loop que lee del self-pipe usa `select.select([pipe_r], [], [], 1.0)`. El timeout de 1 segundo es una decisión deliberada entre dos extremos problemáticos:
- **Timeout 0** (polling): el hilo gira miles de veces por segundo sin hacer nada útil, consumiendo CPU innecesariamente (busy wait).
- **Sin timeout** (bloqueante infinito): si no llega ninguna señal, el hilo queda colgado para siempre y nunca puede detectar que `evento_apagado` fue activado, impidiendo el shutdown limpio.

Con 1 segundo, el hilo duerme eficientemente y despierta a tiempo para chequear la condición de salida cuando el usuario presiona `q`.

### Señales: SIGWINCH dentro del Proceso de la TUI

SIGWINCH (redimensión de terminal) se registra directamente dentro del proceso hijo `proceso_display`, no en el loop central de señales del padre. La razón es la barrera de memoria entre procesos: el objeto `live` de Rich vive en el proceso hijo. Aunque importáramos `_repintar` (un `threading.Event`) desde el padre y lo seteáramos, estaríamos modificando una copia en otro espacio de memoria, sin efecto sobre el proceso hijo.

Para compartir estado entre procesos se requiere IPC (`multiprocessing.Event`, pipes, etc.), lo cual hubiera introducido complejidad innecesaria. Al registrar SIGWINCH localmente dentro del hijo, el handler activa directamente el `threading.Event` correcto, y el loop de `live` llama a `live.refresh()` en la siguiente iteración (máximo 0.25 segundos después).

`Manager.dict` es ideal para el snapshot global porque es un diccionario anidado con estructura variable (usar array serializado sería ineficiente y difícil). Sin embargo, para los intervalos de los analizadores, usar `Manager` introduciría latencia y bloqueo innecesario por cada loop de `time.sleep()`. Por eso, se combinó la arquitectura inyectando 7 objetos `multiprocessing.Value('f')` crudos. Al ser floats compartidos en C sin bloqueos pesados de Manager, los analizadores duermen leyendo esa memoria a altísima velocidad, mientras la TUI la modifica asíncronamente con `+` y `-`.

### TUI: Scroll Adaptativo y Tamaño de Ventana

El diseño inicial intentaba usar `shutil.get_terminal_size()` para calcular cuántos procesos dibujar dinámicamente y permitir el scroll. Sin embargo, en un proceso hijo generado por `multiprocessing`, esto devuelve valores por defecto (ej. 24 líneas). Además, las vistas que contienen datos multilínea (Señales, FDs, Threads) provocaban que Rich truncara la tabla con "..." si se intentaban mostrar demasiados procesos.

La decisión fue implementar una **ventana de scroll de tamaño fijo, pero adaptable por vista**. Las vistas simples (Resumen) muestran 20 procesos, mientras que las vistas densas (Señales) muestran solo 3. El `scroll_offset` se calcula independientemente de la posición del cursor (`cursor_pos`) garantizando que al presionar ↑ o ↓ la vista se desplace de a un elemento por vez, sin saltos ("smooth scrolling") y asegurando que Rich nunca se quede sin espacio para dibujar toda la información.

---

## Conceptos del curso aplicados

*(Se irá completando a medida que avance el TP)*

| Concepto | Dónde se aplica |
|---|---|
| `fork()` y memoria separada | `multiprocessing.Process` — cada analizador tiene su propio espacio de memoria |
| Copy-on-Write (COW) | Razón por la que un `dict` normal no funciona entre procesos |
| Manager / IPC | `snapshot_global` compartido entre todos los procesos |
| GIL | El hilo de teclado es I/O-bound → puede ser thread sin perder paralelismo |
| Estados de proceso (R/S/D/T/Z) | Vista 1 — leído de `/proc/<pid>/stat campo 3` |
| `/proc` filesystem | Fuente de todos los datos del monitor |

---

## Cómo correr y testear

```bash
# Con Docker (recomendado)
docker compose up --build

# Local (requiere Linux)
pip install -r requirements.txt
python3 app.py
```

---

## Lo que aprendí

*(Completar al final del TP)*
