#coding: utf-8
'''
Embedded IPython console widget for QuickNXS.
Uses qtconsole with an in-process kernel.

Originally created on 18-03-2012
author: Paweł Jarosz, Artur Glavic
'''

from qtpy import QtWidgets

from qtconsole.rich_jupyter_widget import RichJupyterWidget
from qtconsole.inprocess import QtInProcessKernelManager
from IPython import get_ipython
from .gui_logging import ip_excepthook_overwrite

class IPythonConsoleQtWidget(RichJupyterWidget):

    def __new__(cls, parent):
      return RichJupyterWidget.__new__(cls)

    def __init__(self, parent):
      from logging import getLogger, CRITICAL
      logger=getLogger()
      silenced=None
      for handler in logger.handlers:
        if handler.__class__.__name__=='QtHandler':
          silenced=handler
          old_level=silenced.level
          silenced.setLevel(CRITICAL+1)
          break
      RichJupyterWidget.__init__(self)
      self._parent=parent
      self.buffer_size=10000 # increase buffer size to show longer outputs
      self.set_default_style(colors='linux')
      kernel_manager=QtInProcessKernelManager(config=self.config, gui='qt')
      kernel_manager.start_kernel()
      self.kernel_manager=kernel_manager
      self.kernel_client=kernel_manager.client()
      self.kernel_client.start_channels()
      ip=get_ipython()
      # console process exceptions (IPython controlled)
      ip.set_custom_exc((Exception,), ip_excepthook_overwrite)
      self.namespace=ip.user_ns
      self.namespace['IP']=self
      self.namespace['app']=QtWidgets.QApplication.instance()
      self.namespace['gui']=parent
      self.namespace['plot']=self._plot
      if silenced:
        silenced.setLevel(old_level)

    def _plot(self, *args, **opts):
      self._parent.ui.refl.clear()
      self._parent.ui.refl.plot(*args, **opts)
      self._parent.ui.refl.draw()
