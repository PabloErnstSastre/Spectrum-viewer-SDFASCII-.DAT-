# -*- coding: utf-8 -*-
"""Lector SDF para el visor HP 35670A.

La librería sdfascii se invoca como comprobación auxiliar cuando está instalada.
El lector local de abajo amplía su comportamiento para procesar cada registro YDATA,
órbitas (pares XY intercalados), límites reales de adquisición y la traza DJOM específica.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import math
import re
import struct
from typing import Any

import numpy as np

APP_NAMES = {10: 'HP 35670A', 9: 'HP 3569A', 8: 'HP 35654A-S1A', 7: 'HP 35635R', 4: 'HP 89410A / 89440A', 3: 'HP 3560A', 2: 'HP 35665A', 1: 'HP 3566A / 3567A', -1: 'HP VISTA', -2: 'HP SINE', -3: 'HP 35660A', -4: 'HP 3562A / 3563A', -5: 'HP 3588A', -6: 'HP 3589A', -99: 'Desconocido'}
DOMAIN_NAMES = {0: 'Frecuencia', 1: 'Tiempo', 2: 'Amplitud', 3: 'RPM', 4: 'Orden', 5: 'Canal', 6: 'Octava'}
TYPE_NAMES = {0:'Desconocido',1:'Espectro lineal',2:'Espectro de potencia automática',3:'Espectro de potencia cruzada',4:'Respuesta en frecuencia',5:'Autocorrelación',6:'Correlación cruzada',7:'Respuesta al impulso',8:'Coherencia ordinaria',9:'Coherencia parcial',10:'Coherencia múltiple',11:'Octava completa',12:'Tercio de octava',13:'Convolución',14:'Histograma',15:'Densidad de probabilidad',16:'Distribución acumulada',17:'Seguimiento de orden: potencia',18:'Seguimiento de orden compuesto',19:'Fase por órdenes',20:'Espectro RPM',21:'Relación de órdenes',22:'Órbita',44:'PSD',45:'Tiempo decimado',47:'Tiempo comprimido',69:'Espectro IQ medido',71:'Espectro IQ de referencia',75:'Vector de error IQ'}
MEAS_NAMES = {-99:'Medida desconocida',0:'Espectro',1:'Red',2:'Barrido',3:'FFT',4:'Órdenes',5:'Octava',6:'Captura',7:'Correlación',8:'Histograma',9:'Red barrida',10:'Red FFT'}
WIN_NAMES = {0:'Sin ventana',1:'Hanning',2:'Flat Top',3:'Uniforme',4:'Force',5:'Response',6:'Definida por usuario',7:'Hamming',8:'P301',9:'P310',10:'Kaiser-Bessel',11:'Harris',12:'Blackman',13:'Filtro de resolución',14:'Correlación lead-lag',15:'Correlación lag',16:'Gated',17:'P400'}
WIN_CORR_NAMES = {0:'No aplicada',1:'Corrección de banda estrecha',2:'Corrección de banda ancha'}


def _i16(data: bytes, off: int) -> int: return struct.unpack_from('>h', data, off)[0]
def _i32(data: bytes, off: int) -> int: return struct.unpack_from('>i', data, off)[0]
def _f32(data: bytes, off: int) -> float: return struct.unpack_from('>f', data, off)[0]
def _f64(data: bytes, off: int) -> float: return struct.unpack_from('>d', data, off)[0]
def _safe_str(data: bytes, off: int, length: int) -> str:
    b = data[off:off+length].split(b'\0', 1)[0]
    return b.decode('latin-1', errors='replace').strip()

def _unit(data: bytes, off: int) -> dict[str, Any]:
    return {'label': _safe_str(data, off, 10), 'factor': _f32(data, off+10),
            'mass': _i16(data, off+14), 'length': _i16(data, off+15), 'time': _i16(data, off+16)}

def _complex_sqrt(z: complex) -> complex:
    # Usar sqrt complejo de Python evita casos límite de parte real negativa.
    return cmath_sqrt(z)

def cmath_sqrt(z: complex) -> complex:
    import cmath
    return cmath.sqrt(z)

@dataclass
class Spectrum:
    filename: str
    title: str
    application: str
    app_code: int
    revision: int
    date: str
    measurement_title: str
    measurement_type: str
    measurement_type_code: int
    domain: str
    domain_code: int
    data_type: str
    data_type_code: int
    complex_data: bool
    is_orbit: bool
    is_djom: bool
    normalized: bool
    power_data: bool
    y_unit: str
    x_unit: str
    channel: str
    module: str
    serial: str
    window: str
    window_correction: str
    narrow_correction: float
    int_to_eng: float
    impedance: float
    corrected_factor: float
    zoom: bool
    start_index: int
    stop_index: int
    first_x: float
    delta_x: float
    x_resolution: str
    x: np.ndarray
    re: np.ndarray
    im: np.ndarray
    full_index: np.ndarray
    raw_points: int
    warning: list[str] = field(default_factory=list)
    sdfascii_status: str = ''

    @property
    def display_name(self) -> str:
        return f'{self.filename} — {self.title}'


def _call_sdfascii_check(path: Path) -> str:
    """Usa sdfascii como verificación secundaria; nunca sustituye el lector extendido.

    sdfascii 0.8.x documenta read_sdf_file(path), pero su lector SDF tiene limitaciones
    publicadas para múltiples registros YDATA y medidas complejas/especiales. Por ello,
    su resultado no se usa como fuente de los datos dibujados.
    """
    try:
        import sdfascii  # type: ignore
    except ImportError:
        return 'sdfascii no instalado; lector SDF integrado activo'
    try:
        reader = getattr(sdfascii, 'read_sdf_file', None)
        if reader is None:
            return 'sdfascii instalado; API de lectura no reconocida, lector integrado activo'
        # La función de sdfascii puede llamar sys.exit() si encuentra un formato no compatible.
        header, values = reader(str(path))
        count = int(np.size(values))
        return f'sdfascii disponible: validación auxiliar ({count} valores del primer registro)'
    except BaseException as exc:  # La librería puede lanzar SystemExit; no debe cerrar la GUI.
        msg = str(exc).strip().replace('\n', ' ')
        return 'sdfascii no pudo validar el archivo; lector SDF integrado activo' + (f' ({msg[:100]})' if msg else '')


def read_sdf(path: str | Path) -> list[Spectrum]:
    path = Path(path)
    data = path.read_bytes()
    if len(data) < 66:
        raise ValueError('Archivo demasiado pequeño para ser un SDF válido.')
    if data[:2] != b'B\0':
        raise ValueError('No se reconoce la firma SDF B\\0. Selecciona el .DAT binario, no .HDR/.TXT.')
    rev, app_code = _i16(data, 8), _i16(data, 10)
    if _i16(data, 2) != 10:
        raise ValueError('El primer registro no es SDF_FILE_HDR.')
    if rev not in (1, 2):
        raise ValueError(f'SDF revisión {rev} no soportada; se admiten las revisiones 1 y 2.')
    counts = {'data': _i16(data, 26), 'vectors': _i16(data, 28), 'channels': _i16(data, 30),
              'scans': _i16(data, 34)}
    offsets = [_i32(data, 38 + j*4) for j in range(7)]
    year, md, hm = _i16(data, 12), _i16(data, 14), _i16(data, 16)
    date = (f'{year}-{md//100:02d}-{md%100:02d} {hm//100:02d}:{hm%100:02d}'
            if year and md > 0 else 'Fecha no disponible')
    meas_off = 66
    if _i16(data, meas_off) != 11:
        raise ValueError('No se encuentra SDF_MEAS_HDR en la posición esperada.')
    meas_size = _i32(data, meas_off+2)
    if meas_size < 128 or meas_off + meas_size > len(data):
        raise ValueError('Cabecera de medida SDF no válida.')
    meas = {
        'zoom': bool(_i16(data, meas_off+22)), 'start': _i16(data, meas_off+24),
        'stop': _i16(data, meas_off+26), 'average': _i16(data, meas_off+28),
        'average_count': _i32(data, meas_off+30), 'title': _safe_str(data, meas_off+38, 60),
        'center': _f64(data, meas_off+102), 'span': _f64(data, meas_off+110),
        'sweep': _f64(data, meas_off+118), 'type': _i16(data, meas_off+126)}

    channels = []
    ch_off = offsets[2]
    for _ in range(max(0, counts['channels'])):
        if ch_off < 0 or ch_off+6 > len(data): break
        size = _i32(data, ch_off+2)
        if _i16(data, ch_off) != 14 or size < 150 or ch_off+size > len(data):
            raise ValueError(f'Cabecera de canal no válida en offset {ch_off}.')
        wc, wcc = _i16(data, ch_off+64), _i16(data, ch_off+66)
        channels.append({'label': _safe_str(data,ch_off+10,30), 'module': _safe_str(data,ch_off+40,12),
                         'serial': _safe_str(data,ch_off+52,12), 'window_code': wc,
                         'window': WIN_NAMES.get(wc, f'Ventana {wc}'), 'window_corr_code': wcc,
                         'window_corr': WIN_CORR_NAMES.get(wcc, f'Código {wcc}'),
                         'narrow': _f32(data,ch_off+84), 'wide': _f32(data,ch_off+80),
                         'unit': _safe_str(data,ch_off+116,10), 'int_to_eng': _f32(data,ch_off+138),
                         'impedance': _f32(data,ch_off+142)})
        ch_off += size

    vectors = []
    v_off = offsets[1]
    for _ in range(max(0, counts['vectors'])):
        if v_off < 0 or v_off+18 > len(data):
            raise ValueError('Cabecera de vector fuera del archivo.')
        size = _i32(data, v_off+2)
        if _i16(data,v_off) != 13 or size < 18 or v_off+size > len(data):
            raise ValueError('Cabecera de vector no válida.')
        vectors.append({'channels': (_i16(data,v_off+10), _i16(data,v_off+12)),
                        'powers': (_i16(data,v_off+14), _i16(data,v_off+16))})
        v_off += size

    data_headers = []
    d_off = offsets[0]
    for _ in range(max(0, counts['data'])):
        if d_off < 0 or d_off+6 > len(data):
            raise ValueError('Cabecera de datos fuera del archivo.')
        size = _i32(data,d_off+2)
        if _i16(data,d_off) != 12 or size < 134 or d_off+size > len(data):
            raise ValueError(f'Cabecera de datos SDF no válida en offset {d_off}.')
        dom, dtype = _i16(data,d_off+26), _i16(data,d_off+28)
        xres, xdt, ydt = _i16(data,d_off+42), _i16(data,d_off+44), _i16(data,d_off+48)
        data_headers.append({'offset': d_off, 'size': size, 'title': _safe_str(data,d_off+10,16),
             'domain_code': dom, 'domain': DOMAIN_NAMES.get(dom, f'Dominio {dom}'),
             'type_code': dtype, 'type': TYPE_NAMES.get(dtype, f'Tipo SDF {dtype}'),
             'num_points': _i16(data,d_off+30), 'last_valid': _i16(data,d_off+32),
             'xres_code': xres, 'x_resolution': ['Lineal','Logarítmica','Arbitraria por archivo','Arbitraria por tipo','Arbitraria por traza'][xres] if 0 <= xres <= 4 else 'Desconocida',
             'x_dtype': xdt, 'y_dtype': ydt, 'y_per_point': _i16(data,d_off+50),
             'complex': bool(_i16(data,d_off+52)), 'normalized': bool(_i16(data,d_off+54)),
             'power': bool(_i16(data,d_off+56)), 'valid': bool(_i16(data,d_off+58)),
             'vector_index': _i32(data,d_off+60), 'x_unit': _unit(data,d_off+68),
             'y_unit_valid': bool(_i16(data,d_off+90)), 'y_unit': _unit(data,d_off+92),
             'first_x': _f64(data,d_off+114) if rev == 2 else _f32(data,d_off+34),
             'delta_x': _f64(data,d_off+122) if rev == 2 else _f32(data,d_off+38),
             'scan_data': bool(_i16(data,d_off+130)) if rev == 2 else False,
             'window_applied': bool(_i16(data,d_off+132)) if rev == 2 else False})
        d_off += size

    y_off = offsets[6]
    if y_off < 0:
        raise ValueError('Este archivo no contiene ningún registro YDATA.')
    scalar_bytes_by_type = {1: 2, 2: 4, 3: 4, 4: 8}
    spectra: list[Spectrum] = []
    sdfascii_status = _call_sdfascii_check(path)
    for dh in data_headers:
        if y_off + 6 > len(data) or _i16(data,y_off) != 17:
            if not spectra: raise ValueError('No se encuentra el registro YDATA esperado.')
            break
        rec_size = _i32(data,y_off+2)
        if rec_size < 6 or y_off+rec_size > len(data):
            raise ValueError('Tamaño de registro YDATA incorrecto.')
        payload = y_off+6
        payload_bytes = rec_size-6
        scalar_bytes = scalar_bytes_by_type.get(dh['y_dtype'])
        if scalar_bytes is None:
            raise ValueError(f'Tipo de dato Y no soportado: código {dh["y_dtype"]}.')
        scalar_count = payload_bytes // scalar_bytes
        is_orbit = dh['type_code'] == 22 or re.match(r'^Orbit$', dh['title'].strip(), re.I) is not None
        is_complex = dh['complex'] or is_orbit
        point_count = min(scalar_count//2, dh['num_points'] or scalar_count//2) if is_orbit else scalar_count // (2 if is_complex else 1)
        formats = {1:'>h', 2:'>i', 3:'>f', 4:'>d'}
        raw_re = np.empty(point_count, dtype=float)
        raw_im = np.zeros(point_count, dtype=float)
        for k in range(point_count):
            if is_orbit:
                raw_re[k] = struct.unpack_from(formats[dh['y_dtype']], data, payload+(2*k)*scalar_bytes)[0]
                raw_im[k] = struct.unpack_from(formats[dh['y_dtype']], data, payload+(2*k+1)*scalar_bytes)[0]
            else:
                raw_re[k] = struct.unpack_from(formats[dh['y_dtype']], data, payload+k*scalar_bytes*(2 if is_complex else 1))[0]
                if is_complex:
                    raw_im[k] = struct.unpack_from(formats[dh['y_dtype']], data, payload+k*scalar_bytes*2+scalar_bytes)[0]
        raw_re[~np.isfinite(raw_re) | (np.abs(raw_re)>1e30)] = np.nan
        raw_im[~np.isfinite(raw_im) | (np.abs(raw_im)>1e30)] = np.nan
        is_djom = (app_code == 10 and dh['domain_code'] == 0 and dh['type_code'] == 2 and re.search(r'DJOM.*SQRT.*SPEC', dh['title'], re.I) is not None)
        vec_index = dh['vector_index']
        vec = vectors[vec_index] if 0 <= vec_index < len(vectors) else (vectors[0] if vectors else None)
        corr = corr_x = corr_y = 1.0
        corr_notes = []
        if vec:
            for ci in range(2):
                ch_id, power = vec['channels'][ci], vec['powers'][ci]
                if ch_id == -1: continue
                if not 0 <= ch_id < len(channels): continue
                ch = channels[ch_id]
                window_corr = ch['narrow'] if dh['domain_code'] in (0,5) else 1.0
                eng_unit = ch['int_to_eng']
                if eng_unit != 0 and math.isfinite(window_corr/eng_unit):
                    factor = (window_corr/eng_unit) ** (power/48.0)
                    if is_orbit:
                        if ci == 0: corr_x *= factor
                        else: corr_y *= factor
                    else: corr *= factor
                else:
                    corr_notes.append('No se aplicó factor de canal: int2engrUnit es cero.')
        real = raw_re * (corr_x if is_orbit else corr)
        imag = raw_im * (corr_y if is_orbit else corr)
        if is_djom:
            velocity_factor = 1000.0 / math.sqrt(2.0)
            real *= velocity_factor
            imag *= velocity_factor
        elif app_code == 10 and not is_orbit:
            if is_complex:
                z = real + 1j*imag
                z_sqrt = np.sqrt(z.astype(complex)) / math.sqrt(2.0)
                real, imag = z_sqrt.real, z_sqrt.imag
            else:
                with np.errstate(invalid='ignore'):
                    real = np.where(real >= 0, np.sqrt(real)/math.sqrt(2.0), np.nan)
                imag = np.zeros_like(real)

        has_bounds = (dh['domain_code'] == 0 and meas['start'] >= 0 and meas['stop'] >= meas['start']
                      and meas['start'] < point_count and meas['stop'] < point_count
                      and (meas['zoom'] or meas['stop'] > meas['start']))
        start = meas['start'] if has_bounds else 0
        stop = min(meas['stop'], point_count-1) if has_bounds else (min(dh['last_valid'],point_count-1) if dh['last_valid']>=0 else point_count-1)
        if stop < start or start >= point_count:
            start, stop = 0, point_count-1
        indices = np.arange(start, stop+1, dtype=int)
        x = dh['first_x'] + indices * dh['delta_x']
        if not len(x): raise ValueError('No hay puntos válidos dentro del rango indicado por los metadatos.')
        v0 = vectors[vec_index] if 0 <= vec_index < len(vectors) else (vectors[0] if vectors else None)
        ch0_id = v0['channels'][0] if v0 else -1
        channel = channels[ch0_id] if 0 <= ch0_id < len(channels) else (channels[0] if channels else {})
        source_unit = (dh['y_unit']['label'] if dh['y_unit_valid'] and dh['y_unit']['label'] else channel.get('unit',''))
        y_unit = 'mm/s' if is_djom else source_unit
        warnings = []
        if not dh['valid']: warnings.append('La cabecera indica que esta traza no es válida.')
        if dh['xres_code'] != 0: warnings.append(f'Eje X {dh["x_resolution"]}: se usan firstX/deltaX declarados si existen.')
        warnings.extend(corr_notes)
        if not is_complex: warnings.append('La traza guardada es real; imaginario/fase pueden no tener significado físico.')
        spectra.append(Spectrum(
            filename=path.name, title=dh['title'] or path.name, application=APP_NAMES.get(app_code, f'Aplicación SDF {app_code}'),
            app_code=app_code, revision=rev, date=date, measurement_title=meas['title'],
            measurement_type=MEAS_NAMES.get(meas['type'],f'Medida {meas["type"]}'), measurement_type_code=meas['type'],
            domain=dh['domain'], domain_code=dh['domain_code'], data_type=dh['type'], data_type_code=dh['type_code'],
            complex_data=is_complex, is_orbit=is_orbit, is_djom=is_djom, normalized=dh['normalized'], power_data=dh['power'],
            y_unit=y_unit or '', x_unit=dh['x_unit']['label'] or dh['domain'], channel=channel.get('label',''),
            module=channel.get('module',''), serial=channel.get('serial',''), window=channel.get('window','No indicada'),
            window_correction=channel.get('window_corr',''), narrow_correction=channel.get('narrow',1.0),
            int_to_eng=channel.get('int_to_eng',1.0), impedance=channel.get('impedance',50.0), corrected_factor=corr,
            zoom=meas['zoom'], start_index=int(start), stop_index=int(stop), first_x=dh['first_x'], delta_x=dh['delta_x'],
            x_resolution=dh['x_resolution'], x=np.asarray(x,dtype=float), re=real[indices], im=imag[indices],
            full_index=indices, raw_points=int(point_count), warning=warnings, sdfascii_status=sdfascii_status))
        y_off += rec_size
    if not spectra: raise ValueError('No se ha extraído ninguna traza Y del archivo.')
    return spectra
