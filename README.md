<img src="organizador/icono.png" alt="TVon" width="96">

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

### Películas de dominio público

Botón **🎞 Dominio público** en la barra superior: busca en la colección de películas del [Internet Archive](https://archive.org/details/feature_films) (unas 25.000, ordenadas por popularidad).

- **Ordenar por** popularidad, título (A → Z / Z → A) o año (más nuevas / más viejas), con el selector o haciendo clic en los encabezados. Al ordenar por año solo aparecen las que tienen año cargado.
- **🗑 Eliminar película**: si una descargada no te gusta, la manda a la Papelera de reciclaje con sus subtítulos, la saca de la biblioteca y la descarga automática no la vuelve a bajar.
- Seleccioná una o varias y **⬇ Descargar** (o doble clic). Se descargan de a una, en la carpeta configurada (por defecto `Videos\TVon`), con barra de progreso.
- Al terminar se agregan a la biblioteca en la categoría **Dominio público**, con subtítulos en español e inglés: de OpenSubtitles si hay clave configurada; en inglés, si no, los del propio Internet Archive (a veces son transcripción automática).
- **Descarga automática**: baja sola las más populares hasta el límite de películas o de GB que elijas. La colección completa ocupa más de 10 TB; siempre se dejan al menos 5 GB libres en el disco.
- Si cerrás TVon a mitad de una descarga, se retoma desde donde quedó al volver a abrirlo.

### Series: siguiente capítulo automático

- Poné los capítulos de una serie en la misma categoría, con números en el nombre (`Cap 1`, `Cap 2`, … `Cap 10`, o `S01E01`).
- 10 segundos antes del final aparece «Siguiente capítulo en 10 s»: al terminar arranca solo, o elegís **Reproducir ahora** o **Cancelar**. La cuenta se frena con la pausa y el aviso se oculta si retrocedés.
- El botón ⏭ (o la tecla N) salta al siguiente capítulo en cualquier momento.
- Los números se ordenan bien: «Cap 2» va antes que «Cap 10», también en la lista.

### Varios videos a la vez

- **Doble clic** en la lista, el botón **⧉ Abrir en ventana** o clic derecho → **Abrir en ventana nueva** abre el archivo en una ventana aparte, que se puede mover, redimensionar y poner en pantalla completa (F / Esc / doble clic).
- Si el video ya se estaba viendo en el visor principal, sigue desde el mismo punto en la ventana.
- Cada ventana tiene su propio volumen, subtítulos y atajos. 📌 la mantiene siempre visible por encima de las demás.

### Subtítulos

- Si junto al video hay un `.srt` o `.vtt` con el mismo nombre (`video.srt`, `video.es.srt`), se carga solo (prefiere español).
- Botón **CC**: cargar otro archivo, cambiar entre los idiomas que haya junto al video, elegir pistas incluidas en el video (p. ej. en .mkv), desactivar y cambiar el tamaño.
- **🌐 Buscar en internet**: descarga subtítulos de [OpenSubtitles](https://www.opensubtitles.com) en los idiomas configurados (por defecto español e inglés). Usa la huella del archivo para encontrar los que están sincronizados con ese video. Hace falta una clave de API gratuita (⚙ Configuración).
- También se puede soltar el `.srt` sobre la ventana.
- **Retraso de subtítulos**: con la casilla bajo los controles o con G / H (±50 ms, como en VLC). Positivo = aparecen más tarde.
- El archivo de subtítulos y el retraso se recuerdan para cada video.

### Atajos

| Tecla | Acción |
|---|---|
| ↑ / ↓ | Archivo anterior / siguiente |
| Espacio | Reproducir / pausar |
| ← / → | Retroceder / adelantar 5 s |
| Shift+← / Shift+→ | Retroceder / adelantar 15 s (también botones ↺15 y 15↻) |
| F o doble clic | Pantalla completa (Esc para salir) |
| N | Siguiente capítulo |
| G / H | Subtítulos 50 ms antes / después |
| Ctrl+F | Buscar |
