"""Prueba de regresión para títulos izquierdo y derecho en el PDF A4."""
from types import SimpleNamespace
import unittest
import numpy as np

from pdf_export import figure_for_spectra


class CustomTitleExportTests(unittest.TestCase):
    def test_source_title_left_and_custom_title_right(self):
        spectrum = SimpleNamespace(title="Lin Spec 2", filename="TRAC20.DAT")
        item = {
            "spectrum": spectrum,
            "x": np.linspace(2, 202, 32),
            "y": np.sin(np.linspace(0, 6, 32)),
            "x_title": "Frecuencia (Hz)",
            "y_title": "Magnitud (mm/s²)",
            "custom_title": "Ensayo bancada A",
            "markers": [],
            "polar": False,
        }
        fig = figure_for_spectra([item])
        try:
            text_positions = {t.get_text(): t.get_position()[0] for t in fig.texts}
            self.assertIn("Lin Spec 2", text_positions)
            self.assertIn("Ensayo bancada A", text_positions)
            self.assertLess(text_positions["Lin Spec 2"], text_positions["Ensayo bancada A"])
            self.assertAlmostEqual(text_positions["Lin Spec 2"], .125)
            self.assertAlmostEqual(text_positions["Ensayo bancada A"], .975)
        finally:
            fig.clear()

    def test_custom_title_is_optional(self):
        spectrum = SimpleNamespace(title="Órbita", filename="TRAC113.DAT")
        item = {"spectrum": spectrum, "x": np.array([0., 1., 0.]),
                "y": np.array([0., 1., 0.]), "x_title": "Time2 (mm)",
                "y_title": "Time1 (mm)", "markers": [], "polar": False}
        fig = figure_for_spectra([item])
        try:
            self.assertIn("Órbita", [t.get_text() for t in fig.texts])
            self.assertFalse(any(t.get_text() == "None" for t in fig.texts))
        finally:
            fig.clear()


if __name__ == "__main__":
    unittest.main()
