#!/bin/bash
# create python files from Qt4 Designer
pyuic4 --from-imports -i 2 designer/main_window.ui -o quick_nxs/main_window.py
pyuic4 --from-imports -i 2 designer/reduce_dialog.ui -o quick_nxs/reduce_dialog.py
pyuic4 --from-imports -i 2 designer/plot_dialog.ui -o quick_nxs/plot_dialog.py
pyuic4 --from-imports -i 2 designer/smooth_dialog.ui -o quick_nxs/smooth_dialog.py
pyuic4 --from-imports -i 2 designer/gisans_dialog.ui -o quick_nxs/gisans_dialog.py
pyuic4 --from-imports -i 2 designer/compare_widget.ui -o quick_nxs/compare_widget.py
pyrcc4 icons/icons.qrc -o quick_nxs/icons_rc.py