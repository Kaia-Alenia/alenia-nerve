# Contribuir a Nerve

En primer lugar, ¡gracias por considerar contribuir a Nerve! Son las personas como tú las que hacen de la comunidad de código abierto un lugar tan grandioso para aprender, inspirar y crear.

## ¿Cómo puedes contribuir?

### Reportar Errores
* Asegúrate de que el error no haya sido reportado previamente buscando en las [Incidencias de GitHub (Issues)](https://github.com/Kaia-Alenia/alenia-nerve/issues).
* Si no encuentras un issue abierto que aborde el problema, crea uno nuevo. Asegúrate de incluir un título y una descripción clara, tanta información relevante como sea posible, y una muestra de código o un caso de prueba ejecutable que demuestre el comportamiento esperado.

### Sugerir Mejoras
* Abre un nuevo [issue](https://github.com/Kaia-Alenia/alenia-nerve/issues/new) con un título y descripción claros.
* Explica por qué esta mejora sería útil para la mayoría de los usuarios.

### Solicitudes de Extracción (Pull Requests)
1. Realiza un fork del repositorio y crea tu rama a partir de `main`.
2. Para el desarrollo del cliente de Python, instala el paquete en modo editable:
   ```bash
   pip install -e clients/python/
   ```
3. Si has agregado código que requiera pruebas, añade pruebas unitarias en el directorio correspondiente del cliente (por ejemplo, `clients/python/tests/`).
4. Asegúrate de que todas las pruebas pasen correctamente.
5. Asegúrate de que tu código respete el formato existente y no tenga errores de sintaxis.
6. ¡Envía tu solicitud de extracción!
