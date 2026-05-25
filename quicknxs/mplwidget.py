#!/usr/bin/env python
import os
import tempfile
import logging
import warnings
from qtpy import QtGui, QtCore, QtWidgets
from qtpy.QtPrintSupport import QPrinter, QPrintPreviewDialog
import matplotlib.cm
import matplotlib.colors
from .config import plotting

# set the default backend to be compatible with Qt in case someone uses pylab from IPython console
matplotlib.use('QtAgg')
def _set_default_rc():
  matplotlib.rc('font', **plotting.font)
  matplotlib.rc('savefig', **plotting.savefig)
_set_default_rc()

cmap=matplotlib.colors.LinearSegmentedColormap.from_list('default',
                  ['#0000ff', '#00ff00', '#ffff00', '#ff0000', '#bd7efc', '#000000'], N=256)
matplotlib.colormaps.register(cmap, name='default')

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas  # noqa: E402
from matplotlib.backends.backend_qt import NavigationToolbar2QT  # noqa: E402
from matplotlib.backend_tools import Cursors as _Cursors  # noqa: E402
from matplotlib.colors import LogNorm, Normalize  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
try:
    import matplotlib.backends.qt_editor.figureoptions as figureoptions
except ImportError:
    figureoptions=None

_log=logging.getLogger(__name__)

# Session-once flag for the expected pcolormesh non-monotonic-coordinate
# warning.  matplotlib emits "coordinates not monotonically increasing or
# decreasing" for the curved, non-rectilinear Q-grids that off-specular maps
# use (and for legitimately overlapping, un-stripped runs).  The mesh still
# renders correctly, so we keep that out of stderr and note it once to the log
# *file* only -- a genuine coordinate bug still leaves a breadcrumb there.
_NONMONOTONIC_NOTED=False


def _note_pcolormesh_warnings(caught):
  '''Triage warnings captured around a pcolormesh draw: swallow the expected
  non-monotonic-coordinate warning (noting it once per session, file-only via
  ``extra={'no_statusbar': True}``) and faithfully re-emit every other warning.'''
  global _NONMONOTONIC_NOTED
  for w in caught:
    if 'monotonic' in str(w.message).lower():
      if not _NONMONOTONIC_NOTED:
        _log.info(u'pcolormesh: non-monotonic coordinates (expected for curved '
                  u'or overlapping off-specular Q-grids); rendering as-is, '
                  u'further occurrences this session suppressed.',
                  extra={'no_statusbar': True})
        _NONMONOTONIC_NOTED=True
    else:
      warnings.warn_explicit(w.message, w.category, w.filename, w.lineno)

class NavigationToolbar(NavigationToolbar2QT):
  '''
    A small change to the original navigation toolbar.
  '''
  _auto_toggle=False

  def __init__(self, canvas, parent, coordinates=False):
    NavigationToolbar2QT.__init__(self, canvas, parent, coordinates)
    self.setIconSize(QtCore.QSize(20, 20))
    self._customize_toolbar()

  def _customize_toolbar(self):
    # Remove default actions built by parent __init__
    for action in self.actions():
      self.removeAction(action)
    # Also remove the locLabel widget the parent may have added
    if hasattr(self, 'locLabel') and self.locLabel is not None:
      self.locLabel.setParent(None)

    # Rebuild with custom icons
    icon=QtGui.QIcon()
    icon.addPixmap(QtGui.QPixmap(":/MPL Toolbar/go-home.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
    a=self.addAction(icon, 'Home', self.home)
    a.setToolTip('Reset original view')
    icon=QtGui.QIcon()
    icon.addPixmap(QtGui.QPixmap(":/MPL Toolbar/zoom-previous.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
    a=self.addAction(icon, 'Back', self.back)
    a.setToolTip('Back to previous view')
    icon=QtGui.QIcon()
    icon.addPixmap(QtGui.QPixmap(":/MPL Toolbar/zoom-next.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
    a=self.addAction(icon, 'Forward', self.forward)
    a.setToolTip('Forward to next view')
    self.addSeparator()
    icon=QtGui.QIcon()
    icon.addPixmap(QtGui.QPixmap(":/MPL Toolbar/transform-move.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
    a=self.addAction(icon, 'Pan', self.pan)
    a.setToolTip('Pan axes with left mouse, zoom with right')
    a.setCheckable(True)
    self._actions['pan']=a
    icon=QtGui.QIcon()
    icon.addPixmap(QtGui.QPixmap(":/MPL Toolbar/zoom-select.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
    a=self.addAction(icon, 'Zoom', self.zoom)
    a.setToolTip('Zoom to rectangle')
    a.setCheckable(True)
    self._actions['zoom']=a
    self.addSeparator()
    icon=QtGui.QIcon()
    icon.addPixmap(QtGui.QPixmap(":/MPL Toolbar/edit-guides.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
    a=self.addAction(icon, 'Subplots', self.configure_subplots)
    a.setToolTip('Configure plot boundaries')

    icon=QtGui.QIcon()
    icon.addPixmap(QtGui.QPixmap(":/MPL Toolbar/document-save.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
    a=self.addAction(icon, 'Save', self.save_figure)
    a.setToolTip('Save the figure')

    icon=QtGui.QIcon()
    icon.addPixmap(QtGui.QPixmap(":/MPL Toolbar/document-print.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
    a=self.addAction(icon, 'Print', self.print_figure)
    a.setToolTip('Print the figure with the default printer')

    icon=QtGui.QIcon()
    icon.addPixmap(QtGui.QPixmap(":/MPL Toolbar/toggle-log.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
    self.addSeparator()
    a=self.addAction(icon, 'Log', self.toggle_log)
    a.setToolTip('Toggle logarithmic scale')

    self.buttons={}

    # Add the x,y location widget at the right side of the toolbar
    # The stretch factor is 1 which means any resizing of the toolbar
    # will resize this label instead of the buttons.
    self.locLabel=QtWidgets.QLabel("", self)
    self.locLabel.setAlignment(
            QtCore.Qt.AlignRight|QtCore.Qt.AlignTop)
    self.locLabel.setSizePolicy(
        QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding,
                          QtWidgets.QSizePolicy.Ignored))
    self.labelAction=self.addWidget(self.locLabel)
    if self.coordinates:
      self.labelAction.setVisible(True)
    else:
      self.labelAction.setVisible(False)

    # reference holder for subplots_adjust window
    self.adj_window=None

  def print_figure(self):
    '''
      Save the plot to a temporary png file and show a preview dialog also used for printing.
    '''
    filetypes=self.canvas.get_supported_filetypes_grouped()
    sorted(filetypes.items())

    filename=os.path.join(tempfile.gettempdir(), u"quicknxs_print.png")
    self.canvas.print_figure(filename, dpi=600)
    imgpix=QtGui.QPixmap(filename)
    os.remove(filename)

    imgobj=QtWidgets.QLabel()
    imgobj.setPixmap(imgpix)
    imgobj.setMask(imgpix.mask())
    imgobj.setGeometry(0, 0, imgpix.width(), imgpix.height())

    def getPrintData(printer):
      imgobj.render(printer)


    printer=QPrinter()
    printer.setPrinterName('mrac4a_printer')
    printer.setPageSize(QPrinter.Letter)
    printer.setResolution(600)
    printer.setOrientation(QPrinter.Landscape)

    pd=QPrintPreviewDialog(printer)
    pd.paintRequested.connect(getPrintData)
    pd.exec_()

  def save_figure(self, *args):
      filetypes=self.canvas.get_supported_filetypes_grouped()
      sorted_filetypes=sorted(filetypes.items())
      default_filetype=self.canvas.get_default_filetype()

      start="image."+default_filetype
      filters=[]
      for name, exts in sorted_filetypes:
          exts_list=" ".join(['*.%s'%ext for ext in exts])
          filter_='%s (%s)'%(name, exts_list)
          if default_filetype in exts:
            filters.insert(0, filter_)
          else:
            filters.append(filter_)
      filters=';;'.join(filters)

      fname=QtWidgets.QFileDialog.getSaveFileName(self, u"Choose a filename to save to", start, filters)[0]
      if fname:
          try:
              self.canvas.print_figure(str(fname))
          except Exception as e:
              QtWidgets.QMessageBox.critical(
                  self, "Error saving file", str(e),
                  QtWidgets.QMessageBox.Ok)

  def toggle_log(self, *args):
    ax=self.canvas.ax
    if len(ax.images)==0 and all([c.__class__.__name__!='QuadMesh' for c in ax.collections]):
      logstate=ax.get_yscale()
      if logstate=='linear':
        ax.set_yscale('log')
      else:
        ax.set_yscale('linear')
      self.canvas.draw()
    else:
      imgs=ax.images+[c for c in ax.collections if c.__class__.__name__=='QuadMesh']
      norm=imgs[0].norm
      if norm.__class__ is LogNorm:
        for img in imgs:
          img.set_norm(Normalize(norm.vmin, norm.vmax))
      else:
        for img in imgs:
          img.set_norm(LogNorm(norm.vmin, norm.vmax))
    self.canvas.draw()

class MplCanvas(FigureCanvas):
  def __init__(self, parent=None, width=3, height=3, dpi=100, sharex=None, sharey=None, adjust={}):
    self.fig=Figure(figsize=(width, height), dpi=dpi, facecolor='#FFFFFF')
    self.ax=self.fig.add_subplot(111, sharex=sharex, sharey=sharey)
    self.fig.subplots_adjust(left=0.15, bottom=0.1, right=0.95, top=0.95)
    self.xtitle=""
    self.ytitle=""
    self.PlotTitle=""
    self.grid_status=True
    self.xaxis_style='linear'
    self.yaxis_style='linear'
    self.format_labels()
    #self.ax.hold(True)
    FigureCanvas.__init__(self, self.fig)
    #self.fc = FigureCanvas(self.fig)
    FigureCanvas.setSizePolicy(self,
                              QtWidgets.QSizePolicy.Expanding,
                              QtWidgets.QSizePolicy.Expanding)
    FigureCanvas.updateGeometry(self)

  def format_labels(self):
    self.ax.set_title(self.PlotTitle)
#    self.ax.title.set_fontsize(10)
#    self.ax.set_xlabel(self.xtitle, fontsize=9)
#    self.ax.set_ylabel(self.ytitle, fontsize=9)
#    labels_x=self.ax.get_xticklabels()
#    labels_y=self.ax.get_yticklabels()
#
#    for xlabel in labels_x:
#      xlabel.set_fontsize(8)
#    for ylabel in labels_y:
#      ylabel.set_fontsize(8)

  def sizeHint(self):
    w, h=self.get_width_height()
    w=max(w, self.height())
    h=max(h, self.width())
    return QtCore.QSize(w, h)

  def minimumSizeHint(self):
    return QtCore.QSize(40, 40)

  def get_default_filetype(self):
      return 'png'


class MPLWidget(QtWidgets.QWidget):
  cplot=None
  cbar=None

  def __init__(self, parent=None, with_toolbar=True, coordinates=False):
    QtWidgets.QWidget.__init__(self, parent)
    self.canvas=MplCanvas()
    self.canvas.ax2=None
    self.vbox=QtWidgets.QVBoxLayout()
    #self.vbox.setMargin(1)
    self.vbox.addWidget(self.canvas)
    if with_toolbar:
      self.toolbar=NavigationToolbar(self.canvas, self)
      self.toolbar.coordinates=coordinates
      self.vbox.addWidget(self.toolbar)
    else:
      self.toolbar=None
    self.setLayout(self.vbox)

  def leaveEvent(self, event):
    '''
    Make sure the cursor is reset to it's default when leaving the widget.
    In some cases the zoom cursor does not reset when leaving the plot.
    '''
    if self.toolbar:
      QtWidgets.QApplication.restoreOverrideCursor()
      self.toolbar._last_cursor=_Cursors.POINTER
    return QtWidgets.QWidget.leaveEvent(self, event)

  def set_config(self, config):
    self.canvas.fig.subplots_adjust(**config)

  def get_config(self):
    spp=self.canvas.fig.subplotpars
    config=dict(left=spp.left,
                right=spp.right,
                bottom=spp.bottom,
                top=spp.top)
    return config


  def draw(self):
    '''
      Convenience to redraw the graph.
    '''
    self.canvas.draw()

  def plot(self, *args, **opts):
    '''
      Convenience wrapper for self.canvas.ax.plot
    '''
    return self.canvas.ax.plot(*args, **opts)

  def semilogy(self, *args, **opts):
    '''
      Convenience wrapper for self.canvas.ax.semilogy
    '''
    return self.canvas.ax.semilogy(*args, **opts)

  def errorbar(self, *args, **opts):
    '''
      Convenience wrapper for self.canvas.ax.semilogy
    '''
    return self.canvas.ax.errorbar(*args, **opts)

  def pcolormesh(self, datax, datay, dataz, log=False, imin=None, imax=None, update=False, **opts):
    '''
      Convenience wrapper for self.canvas.ax.plot
    '''
    # Off-specular Q-grids are curved/non-monotonic by nature; matplotlib's
    # resulting warning is expected noise (see _note_pcolormesh_warnings).
    # Capture warnings around the draw, swallow that one (file-only breadcrumb),
    # re-emit the rest -- without touching coordinates or shading.
    with warnings.catch_warnings(record=True) as caught:
      warnings.simplefilter('always')
      if self.cplot is None or not update:
        if log:
          self.cplot=self.canvas.ax.pcolormesh(datax, datay, dataz, norm=LogNorm(imin, imax), **opts)
        else:
          self.cplot=self.canvas.ax.pcolormesh(datax, datay, dataz, **opts)
      else:
        self.update(datax, datay, dataz)
    _note_pcolormesh_warnings(caught)
    return self.cplot

  def imshow(self, data, log=False, imin=None, imax=None, update=True, **opts):
    '''
      Convenience wrapper for self.canvas.ax.plot
    '''
    if self.cplot is None or not update:
      if log:
        self.cplot=self.canvas.ax.imshow(data, norm=LogNorm(imin, imax), **opts)
      else:
        self.cplot=self.canvas.ax.imshow(data, **opts)
    else:
      self.update(data, **opts)
    return self.cplot

  def set_title(self, new_title):
    return self.canvas.ax.title.set_text(new_title)

  def set_xlabel(self, label):
    return self.canvas.ax.set_xlabel(label)

  def set_ylabel(self, label):
    return self.canvas.ax.set_ylabel(label)

  def set_xscale(self, scale):
    try:
      return self.canvas.ax.set_xscale(scale)
    except ValueError:
      pass

  def set_yscale(self, scale):
    try:
      return self.canvas.ax.set_yscale(scale)
    except ValueError:
      pass

  def clear_fig(self):
    self.cplot=None
    self.cbar=None
    self.canvas.fig.clear()
    self.canvas.ax=self.canvas.fig.add_subplot(111, sharex=None, sharey=None)

  def clear(self):
    self.cplot=None
    self.toolbar._nav_stack.clear()
    self.canvas.ax.clear()
    if self.canvas.ax2 is not None:
      self.canvas.ax2.clear()

  def update(self, *data, **opts):
    self.cplot.set_data(*data)
    if 'extent' in opts:
      self.cplot.set_extent(opts['extent'])
      was_at_home=len(self.toolbar._nav_stack)==0 or \
                  self.toolbar._nav_stack._pos==0
      # reset navigation stack so new extent becomes the home view
      self.toolbar._nav_stack.clear()
      self.canvas.ax.set_xlim(opts['extent'][0], opts['extent'][1])
      self.canvas.ax.set_ylim(opts['extent'][2], opts['extent'][3])
      self.toolbar.push_current()
      if was_at_home:
        self.toolbar._nav_stack._pos=0

  def legend(self, *args, **opts):
    return self.canvas.ax.legend(*args, **opts)

  def adjust(self, **adjustment):
    return self.canvas.fig.subplots_adjust(**adjustment)
