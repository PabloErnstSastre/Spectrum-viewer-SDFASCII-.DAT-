# -*- coding: utf-8 -*-
"""Cálculos de representación equivalentes a la lógica del visor V10."""
from __future__ import annotations
import math
import re
import numpy as np
from sdf_reader import Spectrum


def unit_info(s: Spectrum) -> tuple[float, str]:
    raw = (s.y_unit or '').strip()
    n = raw.lower().replace('μ', 'µ').replace('²', '2').replace('^', '').replace(' ', '')
    known = {
        'm': (1000.0, 'mm'), 'mm': (1.0, 'mm'), 'um': (0.001, 'mm'), 'µm': (0.001, 'mm'),
        'm/s': (1000.0, 'mm/s'), 'mm/s': (1.0, 'mm/s'), 'um/s': (0.001, 'mm/s'), 'µm/s': (0.001, 'mm/s'),
        'm/s2': (1000.0, 'mm/s²'), 'mm/s2': (1.0, 'mm/s²'), 'um/s2': (0.001, 'mm/s²'), 'µm/s2': (0.001, 'mm/s²'),
    }
    return known.get(n, (1.0, raw or 'unidades'))


def orbit_unit_info(s: Spectrum) -> tuple[float, str]:
    raw = (s.y_unit or 'm').strip().lower().replace('μ', 'µ')
    if raw == 'm': return 1000.0, 'mm'
    if raw == 'mm': return 1.0, 'mm'
    if raw in ('um', 'µm'): return 0.001, 'mm'
    return 1.0, s.y_unit or 'unidades'


def linear_amplitude_selectable(s: Spectrum) -> bool:
    return bool(s.app_code == 10 and s.domain_code == 0 and s.data_type_code == 1 and not s.is_orbit and not s.is_djom)


def amplitude_factor(s: Spectrum, mode: str) -> float:
    if not linear_amplitude_selectable(s): return 1.0
    return {'peak': math.sqrt(2.0), 'peak-to-peak': 2.0*math.sqrt(2.0)}.get(mode, 1.0)


def magnitude(s: Spectrum) -> np.ndarray:
    if s.app_code == 10 and s.data_type_code == 1 and s.complex_data and s.domain_code == 0:
        # Convención comprobada en la exportación ASCII del HP 35670A.
        return math.sqrt(2.0) * (s.re**2 + s.im**2)
    return np.hypot(s.re, s.im)


def modulus(s: Spectrum) -> np.ndarray:
    return np.hypot(s.re, s.im)


def phase(s: Spectrum, unwrap: bool = False) -> np.ndarray:
    p = np.degrees(np.arctan2(s.im, s.re))
    return np.degrees(np.unwrap(np.radians(p))) if unwrap else p


def default_type(s: Spectrum) -> str:
    if s.is_orbit: return 'orbit'
    return 'magnitude' if s.complex_data else 'real'


def type_label(kind: str) -> str:
    return {
        'auto':'Auto (HP / metadatos)', 'real':'Real (I)', 'imag':'Imaginario (Q)',
        'magnitude':'Magnitud (HP / ASCII)', 'modulus':'Módulo |Z|', 'logmag':'LogMag',
        'db':'dB', 'dbm':'dBm', 'intensity':'Intensidad |Z|²', 'phase':'Fase',
        'unwrap':'Fase desenrollada', 'nichols':'Nichols (fase / dB)',
        'nyquist':'Vector (Nyquist)', 'orbit':'Órbita (Time2 vs Time1)', 'polar':'Polar'
    }.get(kind, kind)


def plot_vectors(s: Spectrum, kind: str, amplitude_mode: str = 'rms') -> tuple[np.ndarray, np.ndarray, str, str, bool]:
    """Devuelve x, y, títulos X/Y y un booleano de gráfico polar."""
    if kind == 'auto': kind = default_type(s)
    if kind == 'orbit':
        scale, u = orbit_unit_info(s)
        return s.re*scale, s.im*scale, f'Time2 ({u})', f'Time1 ({u})', False
    scale, unit = unit_info(s)
    amp = amplitude_factor(s, amplitude_mode)
    re = s.re * amp
    im = s.im * amp
    mod = modulus(s) * amp
    mag = magnitude(s) * amp
    display_mod = mod * scale
    display_mag = mag * scale
    if kind == 'nyquist':
        return re*scale, im*scale, f'Real / I ({unit})', f'Imaginario / Q ({unit})', False
    if kind == 'nichols':
        return phase(s), 20*np.log10(np.maximum(display_mag, np.finfo(float).tiny)), 'Fase (°)', 'Magnitud (dB)', False
    if kind == 'polar':
        return phase(s), display_mag, 'Fase (°)', f'Magnitud ({unit})', True
    x = s.x
    if kind == 'real': y, ytitle = re*scale, f'Real / I ({unit})'
    elif kind == 'imag': y, ytitle = (im*scale if s.complex_data else np.full_like(s.x, np.nan)), f'Imaginario / Q ({unit})'
    elif kind in ('magnitude','auto'): y, ytitle = (display_mag if s.complex_data else re*scale), f'Magnitud ({unit})'
    elif kind == 'modulus': y, ytitle = display_mod, f'|Z| ({unit})'
    elif kind == 'logmag': y, ytitle = 20*np.log10(np.maximum(display_mag, np.finfo(float).tiny)), 'Magnitud (dB)'
    elif kind == 'db':
        y = (10.0 if s.power_data else 20.0)*np.log10(np.maximum(display_mod**2 if s.power_data else display_mag, np.finfo(float).tiny))
        ytitle = 'Magnitud (dB)'
    elif kind == 'dbm':
        u = (s.y_unit or '').strip().lower()
        if u in ('v','volt','volts'):
            power = mod**2/max(s.impedance,1e-12)
            y = 10*np.log10(np.maximum(power/1e-3,np.finfo(float).tiny))
        elif u in ('w','watt','watts'):
            y = 10*np.log10(np.maximum(mod/1e-3,np.finfo(float).tiny))
        else: y = np.full_like(s.x, np.nan)
        ytitle = 'Potencia (dBm)'
    elif kind == 'intensity': y, ytitle = display_mod**2, f'Intensidad ({unit})²'
    elif kind == 'phase': y, ytitle = phase(s), 'Fase (°)'
    elif kind == 'unwrap': y, ytitle = phase(s, True), 'Fase desenrollada (°)'
    else: y, ytitle = display_mag, f'Amplitud ({unit})'
    xtitle = f'Frecuencia ({s.x_unit or "Hz"})' if s.domain_code == 0 else (f'{s.domain} ({s.x_unit})' if s.x_unit else s.domain)
    if s.domain_code == 1: xtitle = f'Tiempo ({s.x_unit or "s"})'
    if s.domain_code == 4: xtitle = 'Orden'
    if s.domain_code == 3: xtitle = 'RPM'
    if kind in ('phase','unwrap','logmag','db','dbm'): pass
    if linear_amplitude_selectable(s): ytitle += ' · ' + {'peak':'Peak','peak-to-peak':'Peak-to-Peak'}.get(amplitude_mode,'RMS')
    return x, np.asarray(y), xtitle, ytitle, False


def marker_value(s: Spectrum, idx: int, kind: str, amp_mode: str) -> tuple[float, float, str, str]:
    x, y, xt, yt, polar = plot_vectors(s, kind, amp_mode)
    idx = max(0, min(int(idx), len(x)-1))
    return float(x[idx]), float(y[idx]), _title_unit(xt), _title_unit(yt)


def _title_unit(title: str) -> str:
    m = re.search(r'\(([^()]*)\)', title)
    return m.group(1) if m else ('°' if 'Fase' in title else '')
