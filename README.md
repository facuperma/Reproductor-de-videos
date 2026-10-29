<img src="organizador/icono.png" alt="TVon" width="96">

# TVon

Aplicación de escritorio para organizar y ver videos e imágenes por categorías.

## Descargar (Windows 10/11, 64 bits)

**[⬇ TVon-Setup-1.4.5.exe](https://github.com/facuperma/Reproductor-de-videos/raw/main/instalador/TVon-Setup-1.4.5.exe)** (33 MB)

Ejecutalo y seguí los pasos: no hace falta instalar Python ni nada más, ni permisos de administrador. Crea accesos directos en el menú Inicio (y en el Escritorio, si lo elegís) y se desinstala desde *Configuración → Aplicaciones*.

Como el instalador no está firmado digitalmente, Windows puede mostrar «Windows protegió su PC»: tocá **Más información → Ejecutar de todas formas**.

La biblioteca y la configuración se guardan en `%LOCALAPPDATA%\TVon`.

## Desde el código fuente

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Doble clic en `TVon.bat` o `.venv\Scripts\python main.py` (la biblioteca queda en la carpeta del proyecto).

Para generar el instalador: `.venv\Scripts\pip install pyinstaller` y `.venv\Scripts\python empaquetado\construir.py` (requiere [Inno Setup 6](https://jrsoftware.org/isinfo.php)). Queda en `compilado\`. El script baja [aria2](https://aria2.github.io) (motor de torrents) a `organizador\bin\` si no está, y verifica su huella.

## Uso

- **Agregar archivos / carpeta** (o arrastrarlos a la ventana). Las carpetas se recorren con subcarpetas.
- Los archivos no se copian ni se mueven: solo se guarda su ruta en `biblioteca.db`.
- Panel izquierdo: filtrar por Todos / Videos / Imágenes / Sin categoría o por una categoría.
- Seleccioná varios archivos arrastrando el mouse (o con Ctrl/Shift + clic) y con **clic derecho** asignalos a una categoría, quitalos de una o creá una nueva. En «Sin categoría» desaparecen al asignarlos.
- Panel derecho: visor, ruta del archivo, "Abrir ubicación" y las categorías del archivo (se cambian con **✎ Editar**).
- La categoría **★ Favoritos** viene incluida y siempre está primera: sumá archivos con clic derecho → *Agregar a Favoritos*.
- Un clic en un video muestra una **vista previa** (un cuadro del video, sin sonido): se reproduce con clic sobre la imagen, ▶ o Espacio, siempre desde el principio.
- Al elegir una categoría se selecciona su primer video en vista previa, sin empezar a reproducirse.
- Menú superior: **Archivo**, **Vista** (ocultar paneles, pantalla completa), **Configuración**, **Acerca de** (versión) y **Reportar un bug** (abre un issue en GitHub con la versión ya completa).
- Botones **🌐 Películas** ([ext.to](https://ext.to/)) y **🌐 Subtítulos** ([subdivx.com](https://subdivx.com/)) en la barra superior: abren esas páginas en el navegador. Lo que descargues ahí termina en Descargas y TVon lo mueve solo a Videos.

### 📱 ON: manejar TVon desde el celular

Botón **📱 ON** en la barra superior (o *Configuración → ON*; se pone verde mientras está encendido): abre la ventana de ON, donde se ve si está en OFF y se enciende para mostrar el código QR; escanealo con el celular (Android, en Chrome). El celular y la PC tienen que estar en la misma red wifi. Para tenerlo como app: en Chrome, menú ⋮ → *Agregar a la pantalla principal*.

- **Reproductor:** play/pausa, saltos de 5 y 15 s, barra de tiempo, volumen, siguiente capítulo o de la cola, anterior/siguiente de la lista, pantalla completa, *Apagar al terminar* (y cancelar la cuenta para apagar). Muestra lo que se está viendo.
- **Subtítulos:** elegir archivo o pista, desactivarlos, retraso, tamaño y buscar en OpenSubtitles.
- **Cola:** ver, reproducir uno ya, quitar o vaciar.
- **Biblioteca:** buscar, filtrar por categoría, reproducir, encolar, Favoritos, asignar o quitar categorías, crear, renombrar o borrar categorías, *Categoría con el título*, abrir en ventana aparte, quitar de la biblioteca o mandar a la Papelera. Manteniendo apretado se eligen varios.
- **Películas de dominio público:** buscar, ordenar, descargar, la cola de descargas con su progreso y la descarga automática.
- **Mouse:** el celular como touchpad, sin mirar la pantalla (ideal con la PC conectada a la tele): deslizar = mover el puntero, tocar = clic, tocar con dos dedos = clic derecho, deslizar con dos dedos = rueda. Botones **Izquierdo** y **Derecho** (manteniendo el izquierdo y deslizando se arrastra; 🔒 lo deja apretado) y velocidad ajustable.
- **Teclado en vivo:** lo que escribís en el celular aparece en la PC letra por letra, con tildes, ñ, emojis y el autocorrector de Android. También hay modo *Escribir y enviar* y teclas especiales (Enter, Esc, flechas, Alt+Tab, Win, Ctrl+C/V, volumen…).
- **Pantalla:** si hace falta, ves la pantalla de la PC en el celular y la manejás con el dedo: tocar = clic, dos toques = doble clic, mantener = clic derecho, deslizar = rueda, o el modo *Arrastrar*. Con teclado, teclas especiales (Enter, Esc, flechas, Alt+Tab…) y volumen de Windows. Mientras el celular mira la pantalla, TVon lo avisa abajo con un botón para cortar.

Seguridad: el QR lleva un código de emparejamiento; cada celular recibe su propia sesión y se puede desconectar desde la PC (*Desconectar todos*, *Cambiar el código QR*). Compartir la pantalla y manejar el mouse y el teclado se pueden apagar en las opciones de ON. La conexión es solo dentro de la red local y sin cifrar: usalo en tu wifi de casa, no en redes públicas. La primera vez, Windows pregunta por el firewall: hay que tocar **Permitir**.

**Fuera de casa:** con [Tailscale](https://tailscale.com/download) (gratis) instalado en la PC y en el celular con la misma cuenta, en la ventana de ON aparece *🌍 Usarlo fuera de casa* con otro código QR. Así TVon se maneja desde cualquier lado por una conexión cifrada, sin abrir puertos en el router. Si no conecta, permití TVon también en redes públicas en el Firewall de Windows.

### Biblioteca automática

- Los videos de **Videos** y **Documentos** (con subcarpetas) se suman solos a la biblioteca: al abrir TVon y cada minuto. Se saltean carpetas ocultas o de programación (`.venv`, `node_modules`…).
- Los videos que terminan de bajarse en **Descargas** se mueven solos a **Videos** (con sus subtítulos) y entran a la biblioteca. También los de las carpetas que crean los programas de torrents (uTorrent, qBittorrent), si son del último mes; los «sample» se ignoran.
- Si el programa de torrents sigue compartiendo el archivo, la película aparece igual en la biblioteca apenas termina de bajar, y se mueve a Videos cuando el programa la suelta (conserva categorías y subtítulos).
- Todo se ajusta en **⚙ Configuración** (agregar o quitar carpetas, desactivar el movimiento).

### Categoría con el título

Con un solo archivo seleccionado aparece el botón **＋ Categoría: …** (también en el clic derecho). Crea una categoría con el título limpio de la película o serie —«Breaking.Bad.S01E02.720p.mkv» → «Breaking Bad»— y le suma todos los archivos con ese mismo título, así el siguiente capítulo funciona solo. Con **varios** seleccionados, el botón es **＋ Crear categoría: … (n)**: usa el nombre de la serie que más se repite entre ellos y mete en la categoría justo esos archivos. Además ordena el disco: esos videos, con sus subtítulos, pasan a `Videos\Peliculas\<categoría>\` (no se mueven los que se están reproduciendo, los que otro programa tiene abiertos ni los que están en otro disco).

### 🧲 Torrents

Botón **🧲 Torrents** en la barra superior: pegá un link magnet (si lo copiaste, ya aparece pegado), abrí un `.torrent` o soltalo sobre TVon. Muestra la cola con progreso, velocidad y tiempo restante; se puede pausar, reanudar y cancelar (borra lo que había bajado).

- Baja a una carpeta oculta dentro de Videos; al terminar, la película pasa a **Videos**, entra a la biblioteca y se le buscan subtítulos.
- Si cerrás TVon mientras baja, sigue en segundo plano con un ícono junto al reloj de Windows (tocándolo vuelve a abrirse) y se cierra solo cuando terminan las descargas. Con *Salir* en ese ícono se frena todo, y lo que quede a medias se retoma al volver a abrir TVon.
- Usa [aria2](https://aria2.github.io) (GPL v2), que viene incluido. La primera vez, Windows pregunta por el firewall para `aria2c.exe`: tocá **Permitir**.
- Mientras baja, el torrent también se comparte con otros. Al terminar deja de compartir.

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
- Si el capítulo tiene subtítulos, el aviso **Siguiente capítulo** aparece cuando arrancan los créditos (al terminar el último diálogo, en el último tercio del video), para pasar con **Reproducir ahora** sin esperar. Sin subtítulos, aparece 5 segundos antes del final.
- En los últimos 5 segundos cuenta «Siguiente capítulo en 5 s»: al terminar arranca solo, o elegís **Reproducir ahora** o **Cancelar**. La cuenta se frena con la pausa y el aviso se oculta si retrocedés.
- El botón ⏭ (o la tecla N) salta al siguiente capítulo en cualquier momento.
- Los números se ordenan bien: «Cap 2» va antes que «Cap 10», también en la lista.

### Vistos y dónde quedaste

- TVon recuerda hasta dónde viste cada video: al volver a abrirlo sigue desde ahí (la tecla **Inicio** lo arranca desde el principio).
- Un video cuenta como **visto** al pasar el 90 % (los créditos no hace falta verlos). La columna **Visto** muestra ✓ o cuánto llevás («33 % · 5:00»).
- Con algo ya visto, la lista se separa en **Sin ver** y **✓ Vistas**, En **Biblioteca y categorías**, las que tienen algo por ver se ven en amarillo y las que ya viste completas pasan al grupo desplegable **✓ Vistas**, en verde claro (clic en la cabecera para desplegarlo u ocultarlo). Clic en la cabecera de un grupo lo oculta o lo muestra (▸ / ▾); con clic derecho, **Vistas** pasa arriba o abajo. TVon lo recuerda.
- En una serie, al elegir su categoría queda listo el capítulo que dejaste a medias o, si no, el primero sin ver.
- Clic derecho → **Marcar como visto / no visto** para corregirlo a mano. En el celular también aparece el ✓ o el % en la biblioteca.

### Cola de reproducción

- Clic derecho → **☰ Agregar a la cola** suma los videos seleccionados para después del que estás viendo (sin cortarlo). Si no se está viendo nada, arranca el primero.
- La cola va antes que el siguiente capítulo. El botón **☰ Cola (n)** de los controles muestra lo que sigue: reproducir uno ya, quitarlo o vaciar la cola.

### Eliminar videos

**🗑 Eliminar** (al pie de la lista, con algo seleccionado), clic derecho → **Eliminar del disco** o la tecla **Supr**: manda los archivos a la Papelera de reciclaje con sus subtítulos (también el que elegiste a mano, si es solo de ese video) y los quita de la biblioteca. Si la carpeta de la película queda vacía o solo con subtítulos, se va también; si tiene otra cosa (un .txt, fotos…), se deja. Nunca se borran Videos, Descargas ni las carpetas de la biblioteca. Todo se puede recuperar desde la Papelera.

### Apagar al terminar

Marcá **⏻ Apagar** en los controles: cuando termine el video (en el visor o en una ventana aparte) no sigue el próximo y la computadora se apaga tras 60 segundos de aviso, con un botón para **Cancelar**. El apagado cierra los demás programas abiertos sin preguntar. La casilla se desmarca sola después de usarla.

### Varios videos a la vez

- **Doble clic** en la lista, el botón **⧉ Abrir en ventana** o clic derecho → **Abrir en ventana nueva** abre el archivo en una ventana aparte, que se puede mover, redimensionar y poner en pantalla completa (F / Esc / doble clic). La ventana toma el tamaño del video (sin pasarse del 85 % de la pantalla) y se puede achicar a gusto.
- Si el video ya se estaba viendo en el visor principal, sigue desde el mismo punto en la ventana.
- Cada ventana tiene su propio volumen, subtítulos y atajos. 📌 la mantiene siempre visible por encima de las demás.

### Subtítulos

- Si junto al video hay un `.srt` o `.vtt` con el mismo nombre (`video.srt`, `video.es.srt`), se carga solo (prefiere español).
- Botón **CC**: cargar otro archivo, cambiar entre los idiomas que haya junto al video, elegir pistas incluidas en el video (p. ej. en .mkv), desactivar y cambiar el tamaño.
- **🌐 Buscar en internet**: descarga subtítulos de [OpenSubtitles](https://www.opensubtitles.com) en los idiomas configurados (por defecto español e inglés). Usa la huella del archivo para encontrar los que están sincronizados con ese video. Hace falta una clave de API gratuita (⚙ Configuración).
- **Automáticos:** con la clave de OpenSubtitles, cada película nueva (de torrents o de Descargas) recibe sola el subtítulo del primer idioma configurado. Es uno por película, porque la cuenta gratis tiene pocas descargas por día.
- **🌐 Buscar en subdivx** (en el botón CC): abre [subdivx.com](https://subdivx.com/) con el título limpio de la película copiado, y un cartel en la esquina de la pantalla recuerda pegarlo en el buscador con **Ctrl+V**. El subtítulo que bajes (`.srt`, `.zip`, `.rar` o `.7z`) se coloca solo junto al video y se activa. Si el comprimido trae varios, elige el que más se parece al nombre del video. subdivx no tiene API, por eso la descarga la hacés vos.
- También se puede soltar el `.srt` sobre la ventana.
- **Sincronía de subtítulos**: bajo los controles dice cómo salen («1,5 s antes», «sincronizados»). ◀◀ / ◀ los muestran 0,5 / 0,1 s antes; ▶ / ▶▶, después (también G / H). **🎯 Ahora**: tocalo justo cuando alguien empieza a hablar y el subtítulo más cercano se acomoda a ese momento. ↺ vuelve a como viene el archivo.
- El archivo de subtítulos y el retraso se recuerdan para cada video.

### Atajos

| Tecla | Acción |
|---|---|
| ↑ / ↓ | Archivo anterior / siguiente |
| Espacio o clic en el video | Reproducir / pausar |
| ← / → | Retroceder / adelantar 5 s |
| Shift+← / Shift+→ | Retroceder / adelantar 15 s (también botones ↺15 y 15↻) |
| F o doble clic | Pantalla completa (Esc para salir) |
| N | Siguiente de la cola o capítulo |
| Inicio | Volver al principio del video |
| Supr | Eliminar los archivos seleccionados (a la Papelera) |
| G / H | Subtítulos 0,1 s antes / después |
| Ctrl+F | Buscar |

## Licencia

Código abierto bajo la [licencia MIT](LICENSE). © 2026 Faierwall.

Incluye [aria2](https://github.com/aria2/aria2) 1.37.0 sin modificar, como programa aparte, bajo la licencia GPL v2 (`organizador\bin\aria2-LICENCIA.txt`). Su código fuente está en github.com/aria2/aria2.
