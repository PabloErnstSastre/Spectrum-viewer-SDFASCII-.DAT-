# -*- coding: utf-8 -*-
"""Exportación conjunta de hasta cuatro espectros en una única página A4."""
from __future__ import annotations
import math
import re
from pathlib import Path
from typing import Sequence
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_pdf import PdfPages

# Solo el color de las curvas; los marcadores y la interfaz conservan su estilo actual.
SPECTRUM_BLUE = '#2457a6'
MARKER_RED = '#d94841'


def _fmt(v: float) -> str:
    try:
        value = float(v)
    except (TypeError, ValueError):
        return '—'
    if not math.isfinite(value):
        return '—'
    if value != 0 and (abs(value) >= 1e5 or abs(value) < 1e-4):
        return f'{value:.5e}'
    return f'{value:,.7g}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _unit_from_title(title: str) -> str:
    match = re.search(r'\(([^()]*)\)', title or '')
    if match:
        return match.group(1)
    if 'Fase' in title:
        return '°'
    if 'dB' in title:
        return 'dB'
    return ''


def _number_or_none(text) -> float | None:
    try:
        clean = str(text or '').strip().replace(',', '.')
        return float(clean) if clean else None
    except (TypeError, ValueError):
        return None


def _markers_text(item, shown_markers: list[tuple[int, int, float, float]], max_markers: int = 9) -> list[str]:
    """Return compact marker readouts, split into short lines for A4 layouts."""
    xu = _unit_from_title(item.get('x_title', ''))
    yu = _unit_from_title(item.get('y_title', ''))
    parts = [f'M{num}: X={_fmt(x)} {xu}; Y={_fmt(y)} {yu}' for num, _idx, x, y in shown_markers[:max_markers]]
    lines = []
    for i in range(0, len(parts), 2):
        lines.append('    '.join(parts[i:i + 2]))
    remaining = len(shown_markers) - min(len(shown_markers), max_markers)
    if remaining > 0:
        lines.append(f'… {remaining} marcador(es) adicional(es); se mantienen señalados en la gráfica')
    return lines


def figure_for_spectra(items: Sequence[dict]) -> Figure:
    """Create one A4 portrait page holding one to four vertically stacked spectra."""
    items = list(items)
    if not items:
        raise ValueError('Debe proporcionarse al menos un espectro.')
    if len(items) > 4:
        raise ValueError('Solo se pueden imprimir hasta cuatro espectros por página A4.')

    fig = Figure(figsize=(8.2677, 11.6929), dpi=160, facecolor='white')
    n = len(items)
    left, right = .125, .975
    page_top, page_bottom = .965, .045
    gap = .018 if n > 1 else 0.0
    row_h = (page_top - page_bottom - gap * (n - 1)) / n

    for i, item in enumerate(items):
        s = item['spectrum']
        x = np.asarray(item['x'], dtype=float)
        y = np.asarray(item['y'], dtype=float)
        row_top = page_top - i * (row_h + gap)
        row_bottom = row_top - row_h

        markers = []
        for marker_num, idx in enumerate(item.get('markers', []), 1):
            if idx < 0 or idx >= min(len(x), len(y)):
                continue
            xx, yy = float(x[idx]), float(y[idx])
            if math.isfinite(xx) and math.isfinite(yy):
                markers.append((marker_num, idx, xx, yy))

        marker_lines = _markers_text(item, markers)
        # Put compact marker readouts above each plot, leaving the X tick labels
        # and axis title completely clear at the bottom of each panel.
        marker_line_count = len(marker_lines)
        marker_top_band = 0.0 if not marker_lines else (0.022 + 0.012 * marker_line_count)
        title_band = .030 if n > 1 else .035
        ax_bottom = row_bottom + (.040 if n >= 3 else .045)
        ax_top = row_top - title_band - marker_top_band
        ax_height = ax_top - ax_bottom
        if ax_height < .065:
            # Keep the whole report on one page even when many markers are present.
            ax_bottom = row_bottom + .030
            ax_top = row_top - title_band - min(marker_top_band, row_h * .42)
            ax_height = ax_top - ax_bottom

        ax = fig.add_axes([left, ax_bottom, right - left, max(.075, ax_height)],
                          projection='polar' if item.get('polar') else None)
        # Keep the SDF-provided title left-aligned and the user's optional title right-aligned.
        title_font = 8.0 if n >= 3 else (9.0 if n == 2 else 10.5)
        source_title = str(s.title or s.filename)
        fig.text(left, row_top - .006, source_title, ha='left', va='top',
                 fontsize=title_font, fontweight='bold', color='#34101e', clip_on=True)
        custom_title = str(item.get('custom_title') or '').strip()
        if custom_title:
            fig.text(right, row_top - .006, custom_title, ha='right', va='top',
                     fontsize=title_font, fontweight='bold', color='#7e263f', clip_on=True)

        if item.get('polar'):
            ax.set_theta_direction(-1)
            ax.set_theta_offset(math.pi / 2)
            good = np.isfinite(x) & np.isfinite(y)
            if np.any(good):
                ax.plot(np.radians(x[good]), y[good], color=SPECTRUM_BLUE, linewidth=1.0 if n >= 3 else 1.25)
            ax.set_ylabel(item.get('y_title', ''), fontsize=7 if n >= 3 else 8, labelpad=6)
        else:
            good = np.isfinite(x) & np.isfinite(y)
            if item.get('xlog'):
                good &= x > 0
            if item.get('ylog'):
                good &= y > 0
            if np.any(good):
                ax.plot(x[good], y[good], color=SPECTRUM_BLUE, linewidth=0.95 if n >= 3 else 1.2)
            ax.set_xlabel(item.get('x_title', 'X'), fontsize=7 if n >= 3 else 8, labelpad=2)
            ax.set_ylabel(item.get('y_title', 'Y'), fontsize=7 if n >= 3 else 8, labelpad=3)
            if item.get('xlog'):
                ax.set_xscale('log')
            if item.get('ylog'):
                ax.set_yscale('log')

            xlo = _number_or_none(item.get('xmin'))
            xhi = _number_or_none(item.get('xmax'))
            ylo = _number_or_none(item.get('ymin'))
            yhi = _number_or_none(item.get('ymax'))
            try:
                finite_x = x[np.isfinite(x) & ((x > 0) if item.get('xlog') else np.ones(len(x), dtype=bool))]
                if xlo is None and xhi is not None and finite_x.size:
                    xlo = float(np.min(finite_x))
                if xhi is None and xlo is not None and finite_x.size:
                    xhi = float(np.max(finite_x))
                if xlo is not None and xhi is not None and xhi > xlo:
                    ax.set_xlim(xlo, xhi)
                    if item.get('xmin') and item.get('xmax') and not item.get('xlog'):
                        ax.set_xticks([xlo, xhi])

                finite_y = y[np.isfinite(y) & ((y > 0) if item.get('ylog') else np.ones(len(y), dtype=bool))]
                if ylo is None and yhi is not None and finite_y.size:
                    ylo = float(np.min(finite_y))
                if yhi is None and ylo is not None and finite_y.size:
                    yhi = float(np.max(finite_y))
                if ylo is not None and yhi is not None and yhi > ylo:
                    ax.set_ylim(ylo, yhi)
            except (ValueError, OverflowError):
                pass

        ax.grid(True, which='major', color='#dfe4e9', linewidth=.45 if n >= 3 else .55)
        ax.tick_params(labelsize=6.5 if n >= 3 else 7.5, colors='#454047', pad=1)
        for spine in ax.spines.values():
            try:
                spine.set_color('#aeb2b7')
            except Exception:
                pass

        # Markers are placed on the curve and their numeric coordinates are printed
        # in the compact readout area under the corresponding panel.
        for marker_num, _idx, xx, yy in markers:
            if item.get('polar'):
                theta = math.radians(xx)
                ax.plot([theta], [yy], marker='o', color=MARKER_RED, markersize=3.3, linestyle='None', zorder=5)
                ax.annotate(f'M{marker_num}', (theta, yy), xytext=(4, 4), textcoords='offset points',
                            fontsize=5.8 if n >= 3 else 6.8, color='#8b2420')
            else:
                ax.plot([xx], [yy], marker='o', color=MARKER_RED, markersize=3.4, linestyle='None', zorder=5)
                ax.annotate(f'M{marker_num}', (xx, yy), xytext=(4, 4), textcoords='offset points',
                            fontsize=5.8 if n >= 3 else 6.8, color='#8b2420',
                            bbox=dict(boxstyle='round,pad=.13', fc='white', ec=MARKER_RED, alpha=.9),
                            arrowprops=dict(arrowstyle='-', color=MARKER_RED, lw=.45))

        if marker_lines:
            # These lines sit between the panel title and its axes (not beneath the
            # X label); all markers keep their M-number and coordinate readout.
            for line_idx, line in enumerate(marker_lines):
                y_pos = row_top - .026 - line_idx * .012
                fig.text(left, y_pos, line, ha='left', va='top', fontsize=5.5 if n >= 3 else 6.2,
                         color='#342b30', clip_on=True)

    return fig


def figure_for_spectrum(item) -> Figure:
    """Compatibility wrapper: one spectrum on one A4 page."""
    return figure_for_spectra([item])


def export_spectra_pdf(items, output_path: str | Path) -> int:
    """Export all active spectra on one A4 page; returns the number of pages (1)."""
    items = list(items)
    if not items:
        raise ValueError('Debe proporcionarse al menos un espectro.')
    fig = figure_for_spectra(items)
    try:
        with PdfPages(str(output_path), metadata={
            'Title': 'Espectros HP 35670A',
            'Author': 'Pablo Ernst Sastre',
            'Creator': 'Visor de espectros HP 35670A para Python',
        }) as pdf:
            pdf.savefig(fig, facecolor='white')
    finally:
        fig.clear()
    return 1
