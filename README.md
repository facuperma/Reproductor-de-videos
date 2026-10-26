# Organizador multimedia

Aplicación de escritorio para organizar y ver videos e imágenes por categorías.

## Instalación

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Uso

Doble clic en `Abrir.bat` o `.venv\Scripts\python main.py`.

- **Agregar archivos / carpeta** (o arrastrarlos a la ventana). Las carpetas se recorren con subcarpetas.
- Los archivos no se copian ni se mueven: solo se guarda su ruta en `biblioteca.db`.
- Panel izquierdo: filtrar por Todos / Videos / Imágenes / Sin categoría o por una categoría.
- Panel derecho: visor, ruta del archivo, "Abrir ubicación" y casillas para asignar categorías.

### Atajos

| Tecla | Acción |
|---|---|
| ↑ / ↓ | Archivo anterior / siguiente |
| Espacio | Reproducir / pausar |
| ← / → | Retroceder / adelantar 5 s |
| F o doble clic | Pantalla completa (Esc para salir) |
| Ctrl+F | Buscar |
