<img src="organizador/icono.png" alt="TVon" width="96">

# TVon

Aplicación de escritorio para organizar y ver videos e imágenes por categorías.

## Descargar (Windows 10/11, 64 bits)

**[⬇ TVon-Setup-1.1.1.exe](https://github.com/facuperma/Reproductor-de-videos/raw/main/instalador/TVon-Setup-1.1.1.exe)** (28 MB)

Ejecutalo y seguí los pasos: no hace falta instalar Python ni nada más, ni permisos de administrador. Crea accesos directos en el menú Inicio (y en el Escritorio, si lo elegís) y se desinstala desde *Configuración → Aplicaciones*.

Como el instalador no está firmado digitalmente, Windows puede mostrar «Windows protegió su PC»: tocá **Más información → Ejecutar de todas formas**.

La biblioteca y la configuración se guardan en `%LOCALAPPDATA%\TVon`.

## Desde el código fuente

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Doble clic en `TVon.bat` o `.venv\Scripts\python main.py` (la biblioteca queda en la carpeta del proyecto).

Para generar el instalador: `.venv\Scripts\pip install pyinstaller` y `.venv\Scripts\python empaquetado\construir.py` (requiere [Inno Setup 6](https://jrsoftware.org/isinfo.php)). Queda en `compilado\`.

## Uso

- **Agregar archivos / carpeta** (o arrastrarlos a la ventana). Las carpetas se recorren con subcarpetas.
- Los archivos no se copian ni se mueven: solo se guarda su ruta en `biblioteca.db`.
- Panel izquierdo: filtrar por Todos / Videos / Imágenes / Sin categoría o por una categoría.
- Seleccioná varios archivos arrastrando el mouse (o con Ctrl/Shift + clic) y con **clic derecho** asignalos a una categoría, quitalos de una o creá una nueva. En «Sin categoría» desaparecen al asignarlos.
- Panel derecho: visor, ruta del archivo, "Abrir ubicación" y casillas para asignar categorías.
- Un clic en un video muestra una **vista previa** (un cuadro del video, sin sonido): se reproduce con clic sobre la imagen, ▶ o Espacio, siempre desde el principio.
- Al elegir una categoría que tiene **un solo video** (una película), se selecciona solo y, si dura más de una hora, empieza a reproducirse.
- Botones **🌐 Películas** ([ext.to](https://ext.to/)) y **🌐 Subtítulos** ([subdivx.com](https://subdivx.com/)) en la barra superior: abren esas páginas en el navegador. Lo que descargues ahí termina en Descargas y TVon lo mueve solo a Videos.

### Biblioteca automática

- Los videos de **Videos** y **Documentos** (con subcarpetas) se suman solos a la biblioteca: al abrir TVon y cada minuto. Se saltean carpetas ocultas o de programación (`.venv`, `node_modules`…).
- Los videos que terminan de bajarse en **Descargas** se mueven solos a **Videos** (con sus subtítulos) y entran a la biblioteca. Solo archivos sueltos, no subcarpetas, y recién cuando ningún programa los tiene abiertos.
- Todo se ajusta en **⚙ Configuración** (agregar o quitar carpetas, desactivar el movimiento).

### Categoría con el título

Con un solo archivo seleccionado aparece el botón **＋ Categoría: …** (también en el clic derecho). Crea una categoría con el título limpio de la película o serie —«Breaking.Bad.S01E02.720p.mkv» → «Breaking Bad»— y le suma todos los archivos con ese mismo título, así el siguiente capítulo funciona solo.

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
- 5 segundos antes del final aparece «Siguiente capítulo en 5 s»: al terminar arranca solo, o elegís **Reproducir ahora** o **Cancelar**. La cuenta se frena con la pausa y el aviso se oculta si retrocedés.
- El botón ⏭ (o la tecla N) salta al siguiente capítulo en cualquier momento.
- Los números se ordenan bien: «Cap 2» va antes que «Cap 10», también en la lista.

### Cola de reproducción

- Clic derecho → **☰ Agregar a la cola** suma los videos seleccionados para después del que estás viendo (sin cortarlo). Si no se está viendo nada, arranca el primero.
- La cola va antes que el siguiente capítulo. El botón **☰ Cola (n)** de los controles muestra lo que sigue: reproducir uno ya, quitarlo o vaciar la cola.

### Eliminar videos

**🗑 Eliminar** (al pie de la lista, con algo seleccionado), clic derecho → **Eliminar del disco** o la tecla **Supr**: manda los archivos a la Papelera de reciclaje con sus subtítulos y los quita de la biblioteca. Se pueden recuperar desde la Papelera.

### Apagar al terminar

Marcá **⏻ Apagar al terminar** en los controles: cuando termine el video (en el visor o en una ventana aparte) no sigue el próximo y la computadora se apaga tras 60 segundos de aviso, con un botón para **Cancelar**. La casilla se desmarca sola después de usarla.

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
| N | Siguiente de la cola o capítulo |
| Supr | Eliminar los archivos seleccionados (a la Papelera) |
| G / H | Subtítulos 50 ms antes / después |
| Ctrl+F | Buscar |

## Licencia

Código abierto bajo la [licencia MIT](LICENSE). © 2026 Faierwall.
