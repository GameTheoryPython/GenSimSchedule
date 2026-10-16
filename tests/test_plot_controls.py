import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from dataclasses import asdict
from types import SimpleNamespace
from matplotlib import dates as mdates
from PySide6.QtWidgets import QApplication
import pytest

from gensimschedule.gui import Window
from gensimschedule.core import from_metric


def test_plot_limits_zoom_units_and_language():
    app = QApplication.instance() or QApplication([])
    window = Window()
    try:
        window.project.add_well('W1')
        w = window.project.wells[0]
        w.add_node('2025-01-01', 100); w.add_node('2025-12-31', 20)
        window.refresh(); window.list.item(0).setSelected(True)
        before = asdict(window.project)
        window.plot_start.setText('2025/2/1'); window.plot_end.setText('2025-09-01')
        window.plot_min.setText('10'); window.plot_max.setText('120')
        window.apply_plot_limits()
        ax = window.figure.axes[0]
        assert ax.get_xlim() == pytest.approx((mdates.datestr2num('2025-02-01'), mdates.datestr2num('2025-09-01')))
        assert ax.get_ylim() == pytest.approx((10, 120))
        window.set_language('zh')
        assert ax.get_ylim() == pytest.approx((10, 120))
        assert window.plot_start.text() == '2025/2/1'
        assert asdict(window.project) == before
        window.units.setCurrentText('FIELD')
        ax = window.figure.axes[0]
        assert ax.get_ylim() == pytest.approx((from_metric(10, 'FIELD'), from_metric(120, 'FIELD')))
        assert float(window.plot_min.text()) == pytest.approx(from_metric(10, 'FIELD'))
        # Wheel zoom is centered on the pointer and can be reversed through history.
        old_x, old_y = ax.get_xlim(), ax.get_ylim()
        x, y = sum(old_x)/2, sum(old_y)/2
        window.scroll_plot(SimpleNamespace(inaxes=ax, xdata=x, ydata=y, button='up'))
        assert ax.get_xlim()[1] - ax.get_xlim()[0] == pytest.approx((old_x[1]-old_x[0])*.8)
        window.plot_toolbar.back()
        assert ax.get_xlim() == pytest.approx(old_x)
        assert ax.get_ylim() == pytest.approx(old_y)
        window.reset_plot_limits()
        assert not window.plot_start.text() and not window.plot_max.text()
        assert ax.get_xlim() == pytest.approx(window.auto_plot_limits[0])
        assert ax.get_ylim() == pytest.approx(window.auto_plot_limits[1])
        app.processEvents()
    finally:
        window.dirty = False; window.close()


def test_invalid_plot_limits_leave_view_unchanged():
    app = QApplication.instance() or QApplication([])
    window = Window()
    try:
        ax = window.figure.axes[0]
        limits = (ax.get_xlim(), ax.get_ylim(), window.plot_limits)
        window.plot_start.setText('2025-12-01'); window.plot_end.setText('2025-01-01')
        with pytest.raises(ValueError, match='起点'): window.apply_plot_limits()
        assert (ax.get_xlim(), ax.get_ylim(), window.plot_limits) == limits
        window.plot_start.clear(); window.plot_end.clear()
        window.plot_min.setText('nan')
        with pytest.raises(ValueError, match='有限'): window.apply_plot_limits()
        assert (ax.get_xlim(), ax.get_ylim(), window.plot_limits) == limits
        window.plot_min.setText('20'); window.plot_max.setText('10')
        with pytest.raises(ValueError, match='起点'): window.apply_plot_limits()
        assert (ax.get_xlim(), ax.get_ylim(), window.plot_limits) == limits
        app.processEvents()
    finally:
        window.dirty = False; window.close()
