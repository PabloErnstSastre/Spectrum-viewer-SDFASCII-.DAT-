# Visor de espectros HP 35670A / SDF — aplicación Python

**Copyright © 2026 Pablo Ernst Sastre**

Aplicación local de escritorio para cargar archivos binarios `.DAT` del HP/Agilent 35670A, visualizar trazas con hasta cuatro paneles y generar informes PDF A4.

## Requisitos

- Windows 10/11 (la app usa PySide6 y también puede ejecutarse en otros sistemas compatibles con Qt).
- Python 3.11 o 3.12 recomendado (3.13 también puede funcionar con dependencias recientes).
- Acceso a Internet durante la primera instalación de dependencias.

## Instalación y uso rápido en Windows

1. Descomprime todo el ZIP en una carpeta normal (por ejemplo `Documentos\Visor_HP35670A`).
2. Haz doble clic en `INSTALAR.bat`. Se crea un entorno virtual `.venv` y se instalan las dependencias.
3. Haz doble clic en `INICIAR.bat`.
4. Pulsa **Seleccionar archivos .DAT** o arrastra los archivos al programa.
5. Selecciona archivo/traza de forma independiente en cada panel.
6. Pulsa **Imprimir / Guardar PDF** para crear un PDF A4. La aplicación ajusta todos los paneles activos (de uno a cuatro) a una única página A4 vertical; cada gráfico incluye título, ejes y marcadores con lectura numérica.

Para exportar datos tabulares, selecciona una traza y pulsa **Exportar datos CSV**. El CSV se genera con separador `;` y decimales con coma, compatible con Excel en configuración regional española.

## Funciones incluidas en esta primera versión

- Hasta cuatro paneles de gráfica, cada uno con selección independiente de traza.
- Lectura de metadatos embebidos en `.DAT` SDF (revisión 1 y 2) y lista de trazas por archivo.
- Reconocimiento de trazas de frecuencia, la traza calculada `DJOM(SQRT(PSPEC...)` y órbitas con coordenadas intercaladas.
- Representaciones: Auto, Real, Imaginario, Magnitud HP/ASCII, módulo, LogMag, dB, dBm, intensidad, fase, fase desenrollada, Nichols, Nyquist, órbita y polar.
- Espectro lineal HP 35670A: selección RMS / Peak / Peak-to-Peak.
- Ejes lineales/logarítmicos, títulos personalizados para X/Y, título de espectro original alineado a la izquierda y campo de título adicional alineado a la derecha, además de límites X/Y manuales. Cuando se especifican mínimo y máximo X, solo se etiquetan los extremos, como en la V10.
- Marcadores por clic; para mover uno, arrastra el punto rojo a la muestra deseada. Tabla de coordenadas y unidades.
- PDF A4 vertical, con entre uno y cuatro espectros ajustados en una sola página, incluidos marcadores y valores. No imprime los controles de la interfaz.
- Exportación de la traza del panel a CSV con pandas.
- Estilo granate/negro y copyright.

## Lector SDF y `sdfascii`

Se instala `sdfascii==0.8.2`, librería Python publicada para leer ficheros binarios SDF y exportaciones ASCII de analizadores HP/Agilent. La aplicación la consulta como verificación auxiliar cuando está disponible. Para alimentar los gráficos se utiliza además un decodificador ampliado dentro de `sdf_reader.py`, adaptado y probado con los tres casos aportados: espectro lineal (`TRAC20.DAT`), traza `DJOM(SQRT(PSPEC)` (`TRAC1.DAT`) y órbita (`TRAC113.DAT`). Esto evita depender de limitaciones de lectura de un único registro YDATA o de transformaciones genéricas que no se deben aplicar a todas las medidas.

La API y descripción pública de `sdfascii` están en https://pypi.org/project/sdfascii/ y https://github.com/questrail/sdfascii/. El proyecto `sdfascii` declara licencia MIT; consultar su licencia original para los términos del componente de terceros.

**Nota:** en ficheros SDF menos habituales (p. ej. waterfall, datos X arbitrarios, distintos de los formatos probados) la aplicación puede mostrar avisos o necesitar ampliar el decodificador. La vista automática solo puede reconstruir lo que realmente se haya guardado en el archivo.

## Crear un ejecutable

Después de instalar dependencias, ejecuta `CREAR_EXE.bat`. PyInstaller generará `dist\Visor_HP35670A\Visor_HP35670A.exe`. Distribuye la carpeta completa que crea PyInstaller. La compilación debe hacerse en Windows para producir un ejecutable de Windows.

## Estructura

- `main.py`: interfaz gráfica, marcadores y exportaciones.
- `sdf_reader.py`: lectura de SDF y metadatos.
- `spectrum_math.py`: conversiones, unidades y representaciones.
- `requirements.txt`: dependencias.
- `tests/`: pruebas sobre los tres archivos de referencia (se activan si los `.DAT` están disponibles junto al proyecto o mediante `SDF_TEST_DATA`).

## Pruebas

Con las dependencias instaladas:

```powershell
python -m unittest discover -s tests -v
```

© 2026 Pablo Ernst Sastre

### Títulos de los espectros
En cada panel, el título original procedente del archivo SDF aparece alineado a la izquierda. El campo «TÍTULO PERSONALIZADO (OPCIONAL, DERECHA)» permite añadir una etiqueta libre a la derecha. Ambos títulos aparecen también en la exportación PDF.
