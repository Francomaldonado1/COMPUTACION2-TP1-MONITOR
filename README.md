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

### IPC: ¿Por qué `Manager` y no `Value`/`Array`?

`multiprocessing.Value` y `Array` están optimizados para tipos simples (un entero, un float, un arreglo de bytes). El snapshot de este monitor es un diccionario anidado con estructura variable por proceso — usar `Value`/`Array` requeriría serializar manualmente toda la estructura. `Manager.dict` maneja eso de forma transparente a costa de overhead de IPC, que es aceptable dado que los intervalos de refresco son de segundos.

---

## Limitaciones conocidas

- Los filtros por nombre (`/`) y usuario (`u`) están definidos en la TUI pero requieren implementar input inline para ser funcionales.
- El intervalo de refresco de cada vista (ajustable con `+`/`-`) modifica la variable local del display pero aún no comunica el cambio al analizador correspondiente vía `multiprocessing.Value`.

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
