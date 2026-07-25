# Dudas y Consultas del TP

## Sobre la Vista de Señales (Vista 5)
- **Máscaras de Señales de Tiempo Real**: Al leer `/proc/<pid>/status`, procesos del sistema tienen muchas señales de tiempo real (desde la 32 hasta la 64) en estado bloqueadas (`SigBlk`), ignoradas (`SigIgn`) o atrapadas (`SigCgt`). 
  - **Duda**: ¿Se espera que la tabla de la interfaz muestre la lista completa de todas las señales (incluyendo las de tiempo real) decodificadas una por una, o alcanza con detallar por nombre las señales estándar (1 a 31) y dejar las de tiempo real agrupadas como `+ N de tiempo real` para no perjudicar la legibilidad de la vista? Actualmente implementamos la agrupación para evitar que las filas colapsen la terminal.
