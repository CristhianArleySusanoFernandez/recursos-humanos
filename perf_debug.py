"""
[PERF-DEBUG] Instrumentación TEMPORAL de rendimiento.

NO es código permanente. Sirve solo para diagnosticar por qué cada pestaña del
menú tarda ~20 s en cargar. Para quitarlo después basta con:
  1. Eliminar este archivo.
  2. Buscar el marcador `[PERF-DEBUG]` en el proyecto y borrar esas líneas
     (middleware en main.py y los `with timed(...)` / prints en los casos de uso).

Imprime a consola con flush inmediato para ver los tiempos en tiempo real.
"""
from __future__ import annotations

import time
from contextlib import contextmanager


@contextmanager
def timed(label: str):
    """Mide el tiempo de un bloque e imprime `[PERF] label: X ms`."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        dt_ms = (time.perf_counter() - t0) * 1000
        print(f"[PERF]   {label}: {dt_ms:.1f} ms", flush=True)


def log(msg: str) -> None:
    print(f"[PERF]   {msg}", flush=True)
