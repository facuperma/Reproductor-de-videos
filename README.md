# TVon

Aplicación de escritorio para organizar y ver videos e imágenes por categorías.

## Instalación

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Uso

Doble clic en `TVon.bat` o `.venv\Scripts\python main.py`.

- **Agregar archivos / carpeta** (o arrastrarlos a la ventana). Las carpetas se recorren con subcarpetas.
- Los archivos no se copian ni se mueven: solo se guarda su ruta en `biblioteca.db`.
- Panel izquierdo: filtrar por Todos / Videos / Imágenes / Sin categoría o por una categoría.
- Seleccioná varios archivos arrastrando el mouse (o con Ctrl/Shift + clic) y con **clic derecho** asignalos a una categoría, quitalos de una o creá una nueva. En «Sin categoría» desaparecen al asignarlos.
- Panel derecho: visor, ruta del archivo, "Abrir ubicación" y casillas para asignar categorías.

### Varios videos a la vez

- **Doble clic** en la lista, el botón **⧉ Abrir en ventana** o clic derecho → **Abrir en ventana nueva** abre el archivo en una ventana aparte, que se puede mover, redimensionar y poner en pantalla completa (F / Esc / doble clic).
- Si el video ya se estaba viendo en el visor principal, sigue desde el mismo punto en la ventana.
- Cada ventana tiene su propio volumen, subtítulos y atajos. 📌 la mantiene siempre visible por encima de las demás.

### Subtítulos

- Si junto al video hay un `.srt` o `.vtt` con el mismo nombre (`video.srt`, `video.es.srt`), se carga solo.
- Botón **CC**: cargar otro archivo, elegir pistas incluidas en el video (p. ej. en .mkv), desactivar y cambiar el tamaño.
- También se puede soltar el `.srt` sobre la ventana.
- **Retraso de subtítulos**: con la casilla bajo los controles o con G / H (±50 ms, como en VLC). Positivo = aparecen más tarde.
- El archivo de subtítulos y el retraso se recuerdan para cada video.

### Atajos

| Tecla | Acción |
|---|---|
| ↑ / ↓ | Archivo anterior / siguiente |
| Espacio | Reproducir / pausar |
| ← / → | Retroceder / adelantar 5 s |
| F o doble clic | Pantalla completa (Esc para salir) |
| G / H | Subtítulos 50 ms antes / después |
| Ctrl+F | Buscar |
