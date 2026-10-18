# -*- coding: utf-8 -*-
"""Visor de espectros HP 35670A / SDF.
Copyright (c) 2026 Pablo Ernst Sastre.
"""
from __future__ import annotations

import math
import sys
import traceback
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QComboBox,
    QLineEdit, QFileDialog, QMessageBox, QVBoxLayout, QHBoxLayout, QGridLayout,
    QScrollArea, QGroupBox, QFormLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QSpinBox, QSizePolicy, QToolButton, QCheckBox, QStatusBar
)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.ticker import MaxNLocator

from sdf_reader import Spectrum, read_sdf
from pdf_export import export_spectra_pdf, figure_for_spectrum
from spectrum_math import (
    unit_info, orbit_unit_info, linear_amplitude_selectable, amplitude_factor,
    plot_vectors, default_type, type_label, marker_value
)

APP_TITLE = 'Visor de espectros · HP 35670A / SDF'
COPYRIGHT = '© 2026 Pablo Ernst Sastre'
BURGUNDY = '#7e263f'
BURGUNDY_DARK = '#310d1b'
BURGUNDY_LIGHT = '#a94b69'
INK = '#151014'


def _fmt(v: float) -> str:
    try:
        value = float(v)
    except (TypeError, ValueError):
        return '—'
    if not math.isfinite(value): return '—'
    if value != 0 and (abs(value) >= 1e5 or abs(value) < 1e-4):
        return f'{value:.5e}'
    return f'{value:,.7g}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _unit_from_title(title: str) -> str:
    import re
    match = re.search(r'\(([^()]*)\)', title or '')
    if match: return match.group(1)
    if 'Fase' in title: return '°'
    if 'dB' in title: return 'dB'
    return ''


class PlotCanvas(FigureCanvasQTAgg):
    """Canvas interactivo con marcadores de datos arrastrables."""
    def __init__(self, parent=None):
        self.figure = Figure(figsize=(7.2, 3.55), dpi=100, facecolor='white')
        super().__init__(self.figure)
        self.setParent(parent)
        self.setMinimumHeight(285)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)


class SpectrumPanel(QFrame):
    def __init__(self, slot: int, on_export_csv, on_status, parent=None):
        super().__init__(parent)
        self.slot = slot
        self.on_export_csv = on_export_csv
        self.on_status = on_status
        self.spectra: dict[str, Spectrum] = {}
        self.markers: list[int] = []
        self.armed = False
        self.drag_marker: Optional[int] = None
        self.current_key = ''
        self.plot_x_title = 'X'
        self.plot_y_title = 'Y'
        self.current_x = np.array([])
        self.current_y = np.array([])
        self.is_polar = False
        self.ax = None
        self.line = None

        self.setObjectName('spectrumPanel')
        self.setFrameShape(QFrame.Shape.StyledPanel)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(7)

        header = QHBoxLayout()
        self.title_label = QLabel(f'Espectro {slot+1}')
        self.title_label.setObjectName('panelTitle')
        self.slot_label = QLabel(f'SLOT {slot+1:02d}')
        self.slot_label.setObjectName('slotTag')
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.slot_label)
        root.addLayout(header)

        controls = QGridLayout()
        controls.setHorizontalSpacing(8)
        controls.setVerticalSpacing(5)
        self.file_combo = QComboBox()
        self.file_combo.addItem('— carga un archivo .DAT —', '')
        self.file_combo.currentIndexChanged.connect(self._selection_changed)
        self.type_combo = QComboBox()
        self.type_options = [
            ('Auto (HP / metadatos)','auto'), ('Real (I)','real'), ('Imaginario (Q)','imag'),
            ('Magnitud (HP / ASCII)','magnitude'), ('Módulo |Z|','modulus'), ('LogMag','logmag'),
            ('dB','db'), ('dBm','dbm'), ('Intensidad |Z|²','intensity'), ('Fase','phase'),
            ('Fase desenrollada','unwrap'), ('Nichols (fase / dB)','nichols'),
            ('Vector (Nyquist)','nyquist'), ('Órbita (Time2 vs Time1)','orbit'), ('Polar','polar')]
        for label, data in self.type_options: self.type_combo.addItem(label, data)
        self.type_combo.currentIndexChanged.connect(self.redraw)
        self.amplitude_combo = QComboBox()
        self.amplitude_combo.addItem('RMS (predeterminado)', 'rms')
        self.amplitude_combo.addItem('Peak', 'peak')
        self.amplitude_combo.addItem('Peak-to-Peak', 'peak-to-peak')
        self.amplitude_combo.currentIndexChanged.connect(self.redraw)
        self.xscale_combo = QComboBox(); self.xscale_combo.addItems(['Lineal','Logarítmica'])
        self.xscale_combo.currentIndexChanged.connect(self.redraw)
        self.yscale_combo = QComboBox(); self.yscale_combo.addItems(['Lineal','Logarítmica'])
        self.yscale_combo.currentIndexChanged.connect(self.redraw)

        def ctl(label, widget):
            box = QWidget(); lay = QVBoxLayout(box); lay.setContentsMargins(0,0,0,0); lay.setSpacing(2)
            caption = QLabel(label); caption.setObjectName('controlLabel'); lay.addWidget(caption); lay.addWidget(widget)
            return box
        controls.addWidget(ctl('ARCHIVO / TRAZA', self.file_combo), 0,0,1,2)
        controls.addWidget(ctl('REPRESENTACIÓN Y', self.type_combo),0,2)
        self.amp_widget = ctl('UNIDADES DE AMPLITUD',self.amplitude_combo)
        controls.addWidget(self.amp_widget,0,3)
        controls.addWidget(ctl('ESCALA X',self.xscale_combo),1,0)
        controls.addWidget(ctl('ESCALA Y',self.yscale_combo),1,1)
        self.xtitle_edit = QLineEdit(); self.xtitle_edit.setPlaceholderText('Automático según metadatos'); self.xtitle_edit.editingFinished.connect(self.redraw)
        self.ytitle_edit = QLineEdit(); self.ytitle_edit.setPlaceholderText('Automático según unidades'); self.ytitle_edit.editingFinished.connect(self.redraw)
        controls.addWidget(ctl('TÍTULO EJE X (OPCIONAL)',self.xtitle_edit),2,0,1,2)
        controls.addWidget(ctl('TÍTULO EJE Y (OPCIONAL)',self.ytitle_edit),2,2,1,2)
        self.custom_title_edit = QLineEdit()
        self.custom_title_edit.setPlaceholderText('Texto opcional alineado a la derecha del título del espectro')
        self.custom_title_edit.editingFinished.connect(self.redraw)
        controls.addWidget(ctl('TÍTULO PERSONALIZADO (OPCIONAL, DERECHA)',self.custom_title_edit),3,0,1,4)
        root.addLayout(controls)

        axes_box = QGridLayout(); axes_box.setHorizontalSpacing(6); axes_box.setVerticalSpacing(4)
        self.xmin = QLineEdit(); self.xmin.setPlaceholderText('Auto'); self.xmin.setToolTip('Mínimo del eje X; vacío = automático')
        self.xmax = QLineEdit(); self.xmax.setPlaceholderText('Auto'); self.xmax.setToolTip('Máximo del eje X; vacío = automático')
        self.ymin = QLineEdit(); self.ymin.setPlaceholderText('Auto'); self.ymin.setToolTip('Mínimo del eje Y; vacío = automático')
        self.ymax = QLineEdit(); self.ymax.setPlaceholderText('Auto'); self.ymax.setToolTip('Máximo del eje Y; vacío = automático')
        for edit in (self.xmin,self.xmax,self.ymin,self.ymax):
            edit.setMaximumWidth(105); edit.editingFinished.connect(self.redraw)
        axes_box.addWidget(self._axis_field('X MÍN.',self.xmin),0,0)
        axes_box.addWidget(self._axis_field('X MÁX.',self.xmax),0,1)
        axes_box.addWidget(self._axis_field('Y MÍN.',self.ymin),0,2)
        axes_box.addWidget(self._axis_field('Y MÁX.',self.ymax),0,3)
        self.reset_ranges_btn = QPushButton('Auto ejes'); self.reset_ranges_btn.clicked.connect(self.reset_ranges)
        axes_box.addWidget(self.reset_ranges_btn,0,4)
        root.addLayout(axes_box)

        self.metadata_label = QLabel('Carga un archivo .DAT para leer los metadatos.')
        self.metadata_label.setObjectName('metadata')
        self.metadata_label.setWordWrap(True)
        root.addWidget(self.metadata_label)

        self.canvas = PlotCanvas(self)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.toolbar.setIconSize(QSize(16,16))
        root.addWidget(self.canvas, 1)
        root.addWidget(self.toolbar)

        marker_row = QHBoxLayout()
        self.add_marker_btn = QPushButton('Añadir marcador')
        self.add_marker_btn.clicked.connect(self.arm_marker)
        self.clear_marker_btn = QPushButton('Limpiar marcadores')
        self.clear_marker_btn.clicked.connect(self.clear_markers)
        self.marker_note = QLabel('Pulsa «Añadir marcador» y haz clic sobre la curva; arrastra un marcador para moverlo.')
        self.marker_note.setObjectName('muted')
        self.marker_note.setWordWrap(True)
        marker_row.addWidget(self.add_marker_btn)
        marker_row.addWidget(self.clear_marker_btn)
        marker_row.addWidget(self.marker_note,1)
        root.addLayout(marker_row)

        self.marker_table = QTableWidget(0,4)
        self.marker_table.setHorizontalHeaderLabels(['Marcador','X','Y',''])
        self.marker_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.marker_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        self.marker_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        self.marker_table.horizontalHeader().setSectionResizeMode(3,QHeaderView.ResizeMode.ResizeToContents)
        self.marker_table.verticalHeader().setVisible(False)
        self.marker_table.setMaximumHeight(105)
        self.marker_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self.marker_table)

        self.canvas.mpl_connect('button_press_event',self._mouse_press)
        self.canvas.mpl_connect('motion_notify_event',self._mouse_move)
        self.canvas.mpl_connect('button_release_event',self._mouse_release)
        self._show_empty()

    def _axis_field(self, title, edit):
        holder = QWidget(); layout = QVBoxLayout(holder); layout.setContentsMargins(0,0,0,0); layout.setSpacing(2)
        lbl = QLabel(title); lbl.setObjectName('controlLabel'); layout.addWidget(lbl); layout.addWidget(edit)
        return holder

    def set_spectra(self, spectra: dict[str,Spectrum], selected_key: str = ''):
        self.spectra = spectra
        old = selected_key or self.file_combo.currentData() or ''
        self.file_combo.blockSignals(True)
        self.file_combo.clear(); self.file_combo.addItem('— selecciona archivo / traza —','')
        for key,s in spectra.items(): self.file_combo.addItem(s.display_name,key)
        idx = self.file_combo.findData(old)
        self.file_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.file_combo.blockSignals(False)
        self._selection_changed()

    def selected_spectrum(self) -> Optional[Spectrum]:
        key = self.file_combo.currentData()
        return self.spectra.get(key) if key else None

    def selected_type(self) -> str:
        kind = self.type_combo.currentData() or 'auto'
        s = self.selected_spectrum()
        if kind == 'auto' and s and s.is_orbit: return 'orbit'
        return kind

    def selected_amp_mode(self) -> str:
        return self.amplitude_combo.currentData() or 'rms'

    def _selection_changed(self, *args):
        s = self.selected_spectrum()
        key = self.file_combo.currentData() or ''
        if key != self.current_key:
            self.current_key = key
            self.markers.clear()
            self.armed = False; self.drag_marker = None
            self.add_marker_btn.setText('Añadir marcador')
            if s:
                default = default_type(s)
                idx = self.type_combo.findData('orbit' if default == 'orbit' else 'auto')
                self.type_combo.setCurrentIndex(max(0,idx))
                self.amplitude_combo.setCurrentIndex(0)
                self.xmin.clear(); self.xmax.clear(); self.ymin.clear(); self.ymax.clear()
                self.xtitle_edit.clear(); self.ytitle_edit.clear()
        self.redraw()

    def _range(self, low_edit, high_edit, values, logscale=False, x_axis=False):
        def number(edit):
            text = edit.text().strip().replace(',','.')
            if not text: return None
            try:
                val = float(text)
                if not math.isfinite(val): return None
                return val
            except ValueError: return None
        lo, hi = number(low_edit), number(high_edit)
        finite = np.asarray(values, dtype=float)
        finite = finite[np.isfinite(finite)]
        if logscale: finite = finite[finite > 0]
        if lo is None and hi is None: return None
        default_lo = float(np.min(finite)) if finite.size else 1.0
        default_hi = float(np.max(finite)) if finite.size else 10.0
        lo = default_lo if lo is None else lo
        hi = default_hi if hi is None else hi
        if logscale and (lo <= 0 or hi <= 0):
            self.on_status(f'Panel {self.slot+1}: los límites logarítmicos deben ser positivos.')
            return None
        if hi <= lo:
            self.on_status(f'Panel {self.slot+1}: el máximo del eje debe ser mayor que el mínimo.')
            return None
        return lo,hi, (low_edit.text().strip() != '' and high_edit.text().strip() != '')

    def redraw(self, *args):
        s = self.selected_spectrum()
        fig = self.canvas.figure
        fig.clear()
        if not s:
            self.current_x = np.array([]); self.current_y = np.array([]); self.is_polar = False
            self.ax = fig.add_subplot(111)
            self.ax.axis('off')
            self.ax.text(.5,.5,'Carga un archivo .DAT para visualizar el espectro',ha='center',va='center',color='#8090a0',transform=self.ax.transAxes,fontsize=12)
            self.canvas.draw_idle()
            self.metadata_label.setText('Carga un archivo .DAT para leer los metadatos.')
            self.amp_widget.setVisible(False)
            self.marker_table.setRowCount(0)
            return
        kind = self.selected_type()
        amp_mode = self.selected_amp_mode()
        self.amp_widget.setVisible(linear_amplitude_selectable(s))
        x,y,xtitle,ytitle,polar = plot_vectors(s,kind,amp_mode)
        xtitle = self.xtitle_edit.text().strip() or xtitle
        ytitle = self.ytitle_edit.text().strip() or ytitle
        self.plot_x_title, self.plot_y_title = xtitle, ytitle
        self.current_x=np.asarray(x,dtype=float); self.current_y=np.asarray(y,dtype=float); self.is_polar=polar
        if polar:
            self.ax = fig.add_subplot(111, projection='polar')
            self.ax.set_theta_direction(-1); self.ax.set_theta_offset(math.pi/2)
            self.ax.plot(np.radians(x),y,color='#2457a6',linewidth=1.45)
            self.ax.set_ylabel(ytitle,labelpad=15)
        else:
            self.ax = fig.add_subplot(111)
            good = np.isfinite(x) & np.isfinite(y)
            if np.any(good):
                self.line, = self.ax.plot(np.asarray(x)[good],np.asarray(y)[good],color='#2457a6',linewidth=1.35)
            else:
                self.ax.text(.5,.5,'No hay valores finitos para esta representación',ha='center',va='center',transform=self.ax.transAxes)
            self.ax.set_xlabel(xtitle); self.ax.set_ylabel(ytitle)
            if self.xscale_combo.currentIndex() == 1: self.ax.set_xscale('log')
            if self.yscale_combo.currentIndex() == 1: self.ax.set_yscale('log')
            self._apply_limits(self.ax,'x',self.current_x,self.xmin,self.xmax,self.xscale_combo.currentIndex()==1)
            self._apply_limits(self.ax,'y',self.current_y,self.ymin,self.ymax,self.yscale_combo.currentIndex()==1)
            self.ax.margins(x=0.015,y=0.05)
            # If both X bounds are entered, only draw endpoint ticks (V10 behaviour).
            if self.xmin.text().strip() and self.xmax.text().strip():
                try:
                    xticks=[float(self.xmin.text().replace(',','.')),float(self.xmax.text().replace(',','.'))]
                    self.ax.set_xticks(xticks)
                except ValueError: pass
        self.ax.grid(True,which='major',color='#dfe4e9',linewidth=.6)
        self.ax.tick_params(colors='#4a5560',labelsize=8)
        # Título SDF a la izquierda y título libre opcional a la derecha.
        self.ax.set_title(s.title or s.filename,loc='left',color='#2b111b',fontsize=10.5,pad=9)
        custom_title = self.custom_title_edit.text().strip()
        if custom_title:
            self.ax.set_title(custom_title,loc='right',color=BURGUNDY,fontsize=10.5,pad=9)
        for spine in self.ax.spines.values(): spine.set_color('#b7bec5')
        self._draw_markers()
        self.canvas.draw_idle()
        details = [s.filename, s.application, s.measurement_type, s.domain, s.data_type,
                   f'{s.x[0]:g}–{s.x[-1]:g} {s.x_unit or ""} · {len(s.x)} puntos',
                   f'Unidad: {unit_info(s)[1]}',f'Canal: {s.channel or "—"}',f'Ventana: {s.window}']
        if s.warning: details.append('Aviso: '+' '.join(s.warning))
        self.metadata_label.setText('  |  '.join(details))
        self._update_marker_table()

    def _apply_limits(self, ax, axis, values, low_edit, high_edit, logscale):
        bounds = self._range(low_edit,high_edit,values,logscale,axis=='x')
        if not bounds: return
        lo,hi,manual_both=bounds
        if axis=='x':
            ax.set_xlim(lo,hi)
            if manual_both and not logscale:
                ax.set_xticks([lo,hi])
        else:
            ax.set_ylim(lo,hi)
            # Show the manually-entered endpoints as labels as well as intermediate ticks.
            if manual_both and not logscale:
                current = list(ax.get_yticks())
                vals = sorted(set([lo,hi]+[v for v in current if lo < v < hi]))
                ax.set_yticks(vals)

    def _draw_markers(self):
        if self.ax is None or not len(self.current_x): return
        for number, idx in enumerate(self.markers,1):
            idx=max(0,min(idx,len(self.current_x)-1))
            x,y=self.current_x[idx],self.current_y[idx]
            if not math.isfinite(float(x)) or not math.isfinite(float(y)): continue
            if self.is_polar:
                xrad=math.radians(x)
                self.ax.plot([xrad],[y],marker='o',markersize=5,color='#d94841',linestyle='None')
                self.ax.annotate(f'M{number}',(xrad,y),xytext=(7,8),textcoords='offset points',fontsize=8,
                                 color='#8b2420',bbox=dict(boxstyle='round,pad=.2',fc='white',ec='#d94841',alpha=.95))
            else:
                self.ax.plot([x],[y],marker='o',markersize=5,color='#d94841',linestyle='None',zorder=6)
                self.ax.annotate(f'M{number}',(x,y),xytext=(7,8),textcoords='offset points',fontsize=8,
                                 color='#8b2420',bbox=dict(boxstyle='round,pad=.2',fc='white',ec='#d94841',alpha=.95),
                                 arrowprops=dict(arrowstyle='-',color='#d94841',lw=.65))

    def _nearest_index(self, event) -> Optional[int]:
        if self.ax is None or event.xdata is None or event.ydata is None or not len(self.current_x): return None
        x=np.asarray(self.current_x); y=np.asarray(self.current_y)
        valid=np.isfinite(x)&np.isfinite(y)
        if not np.any(valid): return None
        ids=np.flatnonzero(valid)
        # In screen coordinates, this is robust for orbit/Nyquist and uneven scales.
        screen_x = np.radians(x[valid]) if self.is_polar else x[valid]
        pts=self.ax.transData.transform(np.column_stack([screen_x,y[valid]]))
        dist=np.sum((pts-np.array([event.x,event.y]))**2,axis=1)
        return int(ids[int(np.argmin(dist))])

    def _mouse_press(self,event):
        if event.button != 1 or event.inaxes is None or event.inaxes.figure is not self.canvas.figure: return
        if self.armed:
            idx=self._nearest_index(event)
            if idx is not None:
                self.markers.append(idx); self.armed=False
                self.add_marker_btn.setText('Añadir marcador')
                self.marker_note.setText(f'Marcador M{len(self.markers)} añadido. Arrastra el punto rojo para moverlo.')
                self.redraw()
            return
        # Start dragging only when the press is close to an existing marker.
        for mi,idx in enumerate(self.markers):
            if idx>=len(self.current_x): continue
            if not (np.isfinite(self.current_x[idx]) and np.isfinite(self.current_y[idx])): continue
            p=self.ax.transData.transform((self.current_x[idx],self.current_y[idx]))
            if math.hypot(float(p[0]-event.x),float(p[1]-event.y)) <= 12:
                self.drag_marker=mi; return

    def _mouse_move(self,event):
        if self.drag_marker is None or event.inaxes is None or event.inaxes.figure is not self.canvas.figure: return
        idx=self._nearest_index(event)
        if idx is None: return
        self.markers[self.drag_marker]=idx
        self.redraw()

    def _mouse_release(self,event):
        self.drag_marker=None

    def arm_marker(self):
        if self.selected_spectrum() is None:
            self.on_status(f'Panel {self.slot+1}: primero selecciona un archivo o una traza.')
            return
        self.armed = not self.armed
        self.add_marker_btn.setText('Haz clic en la curva…' if self.armed else 'Añadir marcador')
        self.marker_note.setText('Haz clic en la curva para colocar el marcador.' if self.armed else 'Modo de inserción cancelado.')

    def clear_markers(self):
        self.markers.clear(); self.armed=False; self.drag_marker=None
        self.add_marker_btn.setText('Añadir marcador'); self.marker_note.setText('Marcadores eliminados.')
        self.redraw()

    def reset_ranges(self):
        for edit in (self.xmin,self.xmax,self.ymin,self.ymax): edit.clear()
        self.redraw()

    def _update_marker_table(self):
        s=self.selected_spectrum()
        self.marker_table.setRowCount(0)
        if not s: return
        for j,idx in enumerate(self.markers,1):
            x,y, xu,yu=marker_value(s,idx,self.selected_type(),self.selected_amp_mode())
            xu=_unit_from_title(self.current_x_title()) or xu
            yu=_unit_from_title(self.current_y_title()) or yu
            row=self.marker_table.rowCount(); self.marker_table.insertRow(row)
            for col,txt in enumerate((f'M{j}',f'{_fmt(x)} {xu}'.strip(),f'{_fmt(y)} {yu}'.strip(),'')):
                self.marker_table.setItem(row,col,QTableWidgetItem(txt))
            delete=QToolButton(); delete.setText('×'); delete.setToolTip('Eliminar marcador')
            delete.clicked.connect(lambda checked=False, i=j-1: self._remove_marker(i))
            self.marker_table.setCellWidget(row,3,delete)

    def _remove_marker(self, index):
        if 0 <= index < len(self.markers): del self.markers[index]
        self.redraw()

    def export_spec(self):
        s=self.selected_spectrum()
        if not s: return None
        return {'spectrum':s,'kind':self.selected_type(),'amp_mode':self.selected_amp_mode(),
                'x':self.current_x.copy(),'y':self.current_y.copy(),'x_title':self.current_x_title(),
                'y_title':self.current_y_title(),'polar':self.is_polar,'markers':list(self.markers),
                'custom_title':self.custom_title_edit.text().strip(),
                'xmin':self.xmin.text(),'xmax':self.xmax.text(),'ymin':self.ymin.text(),'ymax':self.ymax.text(),
                'xlog':self.xscale_combo.currentIndex()==1,'ylog':self.yscale_combo.currentIndex()==1}

    def current_x_title(self):
        s=self.selected_spectrum()
        if not s:return 'X'
        return self.xtitle_edit.text().strip() or plot_vectors(s,self.selected_type(),self.selected_amp_mode())[2]
    def current_y_title(self):
        s=self.selected_spectrum()
        if not s:return 'Y'
        return self.ytitle_edit.text().strip() or plot_vectors(s,self.selected_type(),self.selected_amp_mode())[3]

    def _show_empty(self):
        self.redraw()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'{APP_TITLE} · escritorio · © Pablo Ernst Sastre')
        self.resize(1500, 1000); self.setMinimumSize(1080,720)
        self.setAcceptDrops(True)
        self.spectra: dict[str,Spectrum] = {}
        self._key_counter=0
        self.setStyleSheet(self._stylesheet())

        central=QWidget(); self.setCentralWidget(central)
        main=QVBoxLayout(central); main.setContentsMargins(10,10,10,8); main.setSpacing(10)
        header=QFrame(); header.setObjectName('maroonHeader'); h=QHBoxLayout(header); h.setContentsMargins(22,15,22,16)
        title=QLabel('Visor de espectros · HP 35670A / SDF'); title.setObjectName('mainTitle')
        self.version_label=QLabel('ESCRITORIO · PYTHON'); self.version_label.setObjectName('versionTag')
        h.addWidget(title); h.addStretch(1); h.addWidget(self.version_label)
        main.addWidget(header)

        top=QFrame(); top.setObjectName('topTools'); tl=QHBoxLayout(top); tl.setContentsMargins(12,9,12,9); tl.setSpacing(8)
        self.load_btn=QPushButton('Seleccionar archivos .DAT'); self.load_btn.setObjectName('loadButton'); self.load_btn.clicked.connect(self.load_files)
        self.panel_count=QComboBox()
        for n in range(1,5): self.panel_count.addItem(f'{n} panel' + ('es' if n>1 else ''),n)
        self.panel_count.setCurrentIndex(3); self.panel_count.currentIndexChanged.connect(self.update_panel_count)
        self.pdf_btn=QPushButton('Imprimir / Guardar PDF'); self.pdf_btn.setObjectName('pdfButton'); self.pdf_btn.clicked.connect(self.export_pdf)
        self.csv_btn=QPushButton('Exportar datos CSV'); self.csv_btn.clicked.connect(self.export_csv)
        self.reset_btn=QPushButton('Restablecer ejes'); self.reset_btn.clicked.connect(self.reset_all_ranges)
        self.load_count_label=QLabel('Sin archivos cargados'); self.load_count_label.setObjectName('muted')
        tl.addWidget(self.load_btn); tl.addSpacing(12); tl.addWidget(QLabel('PANELES')) ; tl.addWidget(self.panel_count)
        tl.addStretch(1); tl.addWidget(self.load_count_label); tl.addWidget(self.csv_btn); tl.addWidget(self.reset_btn); tl.addWidget(self.pdf_btn)
        main.addWidget(top)

        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.panel_container=QWidget(); self.grid=QGridLayout(self.panel_container); self.grid.setContentsMargins(1,1,1,1); self.grid.setSpacing(12)
        self.panels=[]
        for i in range(4):
            panel=SpectrumPanel(i,self.export_csv,self.set_status)
            self.panels.append(panel)
            self.grid.addWidget(panel,i//2,i%2)
        self.scroll.setWidget(self.panel_container); main.addWidget(self.scroll,1)
        footer=QLabel(f'{COPYRIGHT} · Lectura local de SDF · Los .DAT originales no se modifican.')
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter); footer.setObjectName('footer')
        main.addWidget(footer)
        status=QStatusBar(); self.setStatusBar(status); self.status=status
        self.update_panel_count()
        self._build_menus()

    def _stylesheet(self):
        return f'''
        QWidget {{ background:#f5f6f8; color:#211a1d; font-family:"Segoe UI",Arial,sans-serif; font-size:12px; }}
        #maroonHeader {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #09090b,stop:.28 #1b1116,stop:.58 #651b33,stop:.78 #35101c,stop:1 #08090b); border-left:8px solid {BURGUNDY}; border-bottom:4px solid #090709; border-radius:5px 5px 25px 7px; }}
        #mainTitle {{ color:white; font-size:23px; font-weight:700; background:transparent; }}
        #versionTag {{ color:#f1dfe5; background:rgba(126,38,63,.45); border:1px solid #a75a72; border-radius:10px; padding:5px 9px; font-size:10px; font-weight:700; }}
        #topTools {{ background:white; border:1px solid #dcdfe3; border-radius:12px; }}
        #loadButton {{ color:{BURGUNDY}; background:rgba(126,38,63,.08); border:1px dashed rgba(126,38,63,.6); border-radius:9px; padding:9px 13px; font-weight:700; }}
        #loadButton:hover {{ background:rgba(126,38,63,.15); }}
        #pdfButton {{ color:white; background:{BURGUNDY}; border:1px solid {BURGUNDY}; border-left:5px solid {BURGUNDY}; border-bottom:3px solid {BURGUNDY}; border-radius:4px 4px 14px 5px; padding:9px 14px; font-weight:700; }}
        #pdfButton:hover {{ background:#91334f; }}
        QPushButton {{ background:#fff; color:#39212b; border:1px solid #d4c7cc; border-radius:6px; padding:6px 9px; }}
        QPushButton:hover {{ background:#f6edf0; border-color:#9b566b; }}
        QComboBox, QLineEdit {{ background:white; border:1px solid #d6cbd0; border-radius:5px; padding:5px 6px; min-height:19px; selection-background-color:{BURGUNDY}; }}
        #spectrumPanel {{ background:white; border:1px solid #dcdfe3; border-top:3px solid {BURGUNDY}; border-radius:10px; }}
        #panelTitle {{ background:transparent; color:#431122; font-size:15px; font-weight:700; }}
        #slotTag {{ background:#f6e9ee; color:{BURGUNDY}; border-radius:8px; padding:3px 7px; font-size:10px; font-weight:700; }}
        #controlLabel {{ background:transparent; color:#6e5861; font-size:9px; font-weight:700; }}
        #metadata {{ background:#faf7f8; color:#695760; border:1px solid #eee2e7; border-radius:5px; padding:5px; font-size:10px; }}
        #muted, #footer {{ color:#84767c; background:transparent; font-size:10px; }}
        QTableWidget {{ background:white; border:1px solid #eee2e7; border-radius:5px; gridline-color:#efe6e9; }}
        QHeaderView::section {{ background:#f7edf1; color:#64233a; border:0; border-bottom:1px solid #e8d4dc; padding:4px; font-weight:700; }}
        QToolButton {{ background:#fff; color:{BURGUNDY}; border:1px solid #ead3dc; border-radius:4px; }}
        QScrollArea {{ background:transparent; }}
        '''

    def _build_menus(self):
        menu=self.menuBar().addMenu('Archivo')
        action_load=QAction('Cargar archivos .DAT…',self); action_load.triggered.connect(self.load_files); menu.addAction(action_load)
        action_pdf=QAction('Imprimir / Guardar PDF…',self); action_pdf.triggered.connect(self.export_pdf); menu.addAction(action_pdf)
        action_csv=QAction('Exportar CSV…',self); action_csv.triggered.connect(self.export_csv); menu.addAction(action_csv)
        menu.addSeparator(); action_exit=QAction('Salir',self); action_exit.triggered.connect(self.close); menu.addAction(action_exit)
        about=self.menuBar().addMenu('Ayuda')
        act=QAction('Acerca de…',self); act.triggered.connect(lambda: QMessageBox.about(self,APP_TITLE,f'{APP_TITLE}\nVersión de escritorio inicial\n{COPYRIGHT}\n\nLectura SDF con apoyo opcional de sdfascii.')); about.addAction(act)

    def set_status(self,text):
        self.status.showMessage(str(text),8000)

    def update_panel_count(self,*args):
        count=int(self.panel_count.currentData() or 4)
        for i,p in enumerate(self.panels): p.setVisible(i<count)
        # Qt grid positioning remains 2 columns, so 3 panels show 2+1 and 4 show 2x2.
        for i,p in enumerate(self.panels): self.grid.addWidget(p,i//2,i%2)

    def load_files(self, paths=None):
        if paths is None:
            paths,_=QFileDialog.getOpenFileNames(self,'Seleccionar archivos binarios SDF','', 'Archivos SDF (*.DAT *.dat *.SDF *.sdf);;Todos los archivos (*.*)')
        if not paths: return
        added=[]; errors=[]
        for name in paths:
            try:
                items=read_sdf(name)
                for item in items:
                    key=f'{Path(name).resolve()}::{item.title}::{self._key_counter}'
                    self._key_counter+=1
                    self.spectra[key]=item; added.append(key)
            except Exception as exc:
                errors.append(f'{Path(name).name}: {exc}')
                traceback.print_exc()
        if not self.spectra:
            QMessageBox.warning(self,'No se han podido cargar archivos','\n'.join(errors) or 'No se encontraron trazas SDF válidas.')
            return
        # Update the file/trace list in each panel while preserving previous choices.
        for p in self.panels:
            p.set_spectra(self.spectra, str(p.file_combo.currentData() or ''))
        # Put newly loaded traces into currently empty visible panels, one per panel.
        empty_panels=[p for p in self.panels[:int(self.panel_count.currentData())] if not p.file_combo.currentData()]
        for p,key in zip(empty_panels,added):
            idx=p.file_combo.findData(key)
            if idx>=0: p.file_combo.setCurrentIndex(idx)
        self.load_count_label.setText(f'{len(self.spectra)} traza(s) cargada(s)')
        msg=f'Carga finalizada: {len(added)} traza(s) nueva(s), {len(self.spectra)} en total.'
        if errors: msg += ' Errores: ' + ' | '.join(errors)
        self.set_status(msg)
        if errors: QMessageBox.warning(self,'Carga con avisos',msg)

    def reset_all_ranges(self):
        for p in self.panels: p.reset_ranges()
        self.set_status('Se han restablecido los límites de los ejes.')

    def export_csv(self):
        # Export selected panel if invoked from the global toolbar.
        panel=None
        for p in self.panels:
            if p.isVisible() and p.selected_spectrum() is not None:
                panel=p; break
        if panel is None:
            QMessageBox.information(self,'Exportar CSV','Selecciona una traza en uno de los paneles antes de exportar.'); return
        spec=panel.export_spec()
        if not spec: return
        s=spec['spectrum']
        default=Path(s.filename).with_suffix('').name + '_datos.csv'
        out,_=QFileDialog.getSaveFileName(self,'Exportar datos de la traza',default,'CSV (*.csv)')
        if not out:return
        try:
            n=len(s.x)
            df=pd.DataFrame({'X original SDF':s.x,'Unidad X original':s.x_unit,
                             'X representada':spec['x'],'Y representada':spec['y'],
                             'Real corregida':s.re,'Imaginaria corregida':s.im,
                             'Módulo complejo':np.hypot(s.re,s.im)})
            df.to_csv(out,index=False,encoding='utf-8-sig',sep=';',decimal=',')
            self.set_status(f'CSV guardado: {out}')
        except Exception as exc:
            QMessageBox.critical(self,'Error al exportar CSV',str(exc))

    def export_pdf(self):
        specs=[]
        for panel in self.panels[:int(self.panel_count.currentData() or 4)]:
            item=panel.export_spec()
            if item is not None: specs.append(item)
        if not specs:
            QMessageBox.information(self,'Imprimir / Guardar PDF','Carga al menos una traza en un panel.'); return
        default='espectros_hp35670a.pdf'
        out,_=QFileDialog.getSaveFileName(self,'Guardar espectros como PDF A4',default,'Documento PDF (*.pdf)')
        if not out:return
        if not out.lower().endswith('.pdf'):out += '.pdf'
        try:
            export_spectra_pdf(specs, out)
            self.set_status(f'PDF A4 creado: {out} · {len(specs)} espectro(s) en una página')
            QMessageBox.information(self,'PDF creado',f'Archivo guardado correctamente:\n{out}\n\n{len(specs)} espectro(s) ajustado(s) a una única página A4, con títulos, ejes y marcadores.')
        except Exception as exc:
            QMessageBox.critical(self,'Error al crear PDF',f'No se pudo generar el PDF:\n{exc}')

    def _pdf_figure(self,item):
        return figure_for_spectrum(item)

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls():event.acceptProposedAction()
        else:event.ignore()
    def dropEvent(self,event):
        paths=[u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile() and Path(u.toLocalFile()).suffix.lower() in ('.dat','.sdf')]
        if paths:self.load_files(paths);event.acceptProposedAction()
        else:event.ignore()


def main():
    app=QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setOrganizationName('Pablo Ernst Sastre')
    window=MainWindow();window.show()
    return app.exec()

if __name__=='__main__':
    raise SystemExit(main())
