# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'designer/plot_dialog_refl.ui'
#
# Created: Thu Dec  4 10:37:58 2014
#      by: PyQt4 UI code generator 4.7.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Dialog(object):
    def setupUi(self, Dialog):
        Dialog.setObjectName("Dialog")
        Dialog.resize(1232, 1001)
        self.horizontalLayout_2 = QtGui.QHBoxLayout(Dialog)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.tabWidget = QtGui.QTabWidget(Dialog)
        self.tabWidget.setObjectName("tabWidget")
        self.tab = QtGui.QWidget()
        self.tab.setObjectName("tab")
        self.horizontalLayout = QtGui.QHBoxLayout(self.tab)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.plot_pixel_vs_counts = MPLWidget(self.tab)
        self.plot_pixel_vs_counts.setObjectName("plot_pixel_vs_counts")
        self.horizontalLayout.addWidget(self.plot_pixel_vs_counts)
        self.groupBox_4 = QtGui.QGroupBox(self.tab)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.groupBox_4.sizePolicy().hasHeightForWidth())
        self.groupBox_4.setSizePolicy(sizePolicy)
        self.groupBox_4.setObjectName("groupBox_4")
        self.verticalLayout_11 = QtGui.QVBoxLayout(self.groupBox_4)
        self.verticalLayout_11.setObjectName("verticalLayout_11")
        self.frame = QtGui.QFrame(self.groupBox_4)
        self.frame.setFrameShape(QtGui.QFrame.StyledPanel)
        self.frame.setFrameShadow(QtGui.QFrame.Raised)
        self.frame.setObjectName("frame")
        self.verticalLayout_12 = QtGui.QVBoxLayout(self.frame)
        self.verticalLayout_12.setObjectName("verticalLayout_12")
        self.horizontalLayout_15 = QtGui.QHBoxLayout()
        self.horizontalLayout_15.setObjectName("horizontalLayout_15")
        self.john_slider_peak2 = QtGui.QSlider(self.frame)
        self.john_slider_peak2.setMaximum(303)
        self.john_slider_peak2.setOrientation(QtCore.Qt.Vertical)
        self.john_slider_peak2.setObjectName("john_slider_peak2")
        self.horizontalLayout_15.addWidget(self.john_slider_peak2)
        self.verticalLayout_13 = QtGui.QVBoxLayout()
        self.verticalLayout_13.setObjectName("verticalLayout_13")
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.verticalLayout_13.addItem(spacerItem)
        self.john_peak2 = QtGui.QSpinBox(self.frame)
        self.john_peak2.setMaximum(303)
        self.john_peak2.setObjectName("john_peak2")
        self.verticalLayout_13.addWidget(self.john_peak2)
        self.horizontalLayout_15.addLayout(self.verticalLayout_13)
        self.verticalLayout_12.addLayout(self.horizontalLayout_15)
        self.horizontalLayout_16 = QtGui.QHBoxLayout()
        self.horizontalLayout_16.setObjectName("horizontalLayout_16")
        self.john_slider_peak1 = QtGui.QSlider(self.frame)
        self.john_slider_peak1.setMaximum(303)
        self.john_slider_peak1.setOrientation(QtCore.Qt.Vertical)
        self.john_slider_peak1.setObjectName("john_slider_peak1")
        self.horizontalLayout_16.addWidget(self.john_slider_peak1)
        self.verticalLayout_14 = QtGui.QVBoxLayout()
        self.verticalLayout_14.setObjectName("verticalLayout_14")
        self.john_peak1 = QtGui.QSpinBox(self.frame)
        self.john_peak1.setMaximum(303)
        self.john_peak1.setObjectName("john_peak1")
        self.verticalLayout_14.addWidget(self.john_peak1)
        spacerItem1 = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.verticalLayout_14.addItem(spacerItem1)
        self.horizontalLayout_16.addLayout(self.verticalLayout_14)
        self.verticalLayout_12.addLayout(self.horizontalLayout_16)
        self.verticalLayout_11.addWidget(self.frame)
        self.horizontalLayout.addWidget(self.groupBox_4)
        self.groupBox_3 = QtGui.QGroupBox(self.tab)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.groupBox_3.sizePolicy().hasHeightForWidth())
        self.groupBox_3.setSizePolicy(sizePolicy)
        self.groupBox_3.setObjectName("groupBox_3")
        self.verticalLayout_8 = QtGui.QVBoxLayout(self.groupBox_3)
        self.verticalLayout_8.setObjectName("verticalLayout_8")
        self.frame_2 = QtGui.QFrame(self.groupBox_3)
        self.frame_2.setFrameShape(QtGui.QFrame.StyledPanel)
        self.frame_2.setFrameShadow(QtGui.QFrame.Raised)
        self.frame_2.setObjectName("frame_2")
        self.verticalLayout_7 = QtGui.QVBoxLayout(self.frame_2)
        self.verticalLayout_7.setObjectName("verticalLayout_7")
        self.horizontalLayout_13 = QtGui.QHBoxLayout()
        self.horizontalLayout_13.setObjectName("horizontalLayout_13")
        self.john_slider_back2 = QtGui.QSlider(self.frame_2)
        self.john_slider_back2.setMaximum(303)
        self.john_slider_back2.setOrientation(QtCore.Qt.Vertical)
        self.john_slider_back2.setObjectName("john_slider_back2")
        self.horizontalLayout_13.addWidget(self.john_slider_back2)
        self.verticalLayout_9 = QtGui.QVBoxLayout()
        self.verticalLayout_9.setObjectName("verticalLayout_9")
        spacerItem2 = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.verticalLayout_9.addItem(spacerItem2)
        self.john_back2 = QtGui.QSpinBox(self.frame_2)
        self.john_back2.setMaximum(303)
        self.john_back2.setObjectName("john_back2")
        self.verticalLayout_9.addWidget(self.john_back2)
        spacerItem3 = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.verticalLayout_9.addItem(spacerItem3)
        self.horizontalLayout_13.addLayout(self.verticalLayout_9)
        self.verticalLayout_7.addLayout(self.horizontalLayout_13)
        self.horizontalLayout_14 = QtGui.QHBoxLayout()
        self.horizontalLayout_14.setObjectName("horizontalLayout_14")
        self.john_slider_back1 = QtGui.QSlider(self.frame_2)
        self.john_slider_back1.setMaximum(303)
        self.john_slider_back1.setOrientation(QtCore.Qt.Vertical)
        self.john_slider_back1.setObjectName("john_slider_back1")
        self.horizontalLayout_14.addWidget(self.john_slider_back1)
        self.verticalLayout_10 = QtGui.QVBoxLayout()
        self.verticalLayout_10.setObjectName("verticalLayout_10")
        spacerItem4 = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.verticalLayout_10.addItem(spacerItem4)
        self.john_back1 = QtGui.QSpinBox(self.frame_2)
        self.john_back1.setMaximum(303)
        self.john_back1.setObjectName("john_back1")
        self.verticalLayout_10.addWidget(self.john_back1)
        spacerItem5 = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.verticalLayout_10.addItem(spacerItem5)
        self.horizontalLayout_14.addLayout(self.verticalLayout_10)
        self.verticalLayout_7.addLayout(self.horizontalLayout_14)
        self.verticalLayout_8.addWidget(self.frame_2)
        self.horizontalLayout.addWidget(self.groupBox_3)
        self.tabWidget.addTab(self.tab, "")
        self.tab_2 = QtGui.QWidget()
        self.tab_2.setObjectName("tab_2")
        self.verticalLayout = QtGui.QVBoxLayout(self.tab_2)
        self.verticalLayout.setObjectName("verticalLayout")
        self.plot_counts_vs_pixel = MPLWidget(self.tab_2)
        self.plot_counts_vs_pixel.setObjectName("plot_counts_vs_pixel")
        self.verticalLayout.addWidget(self.plot_counts_vs_pixel)
        self.groupBox = QtGui.QGroupBox(self.tab_2)
        self.groupBox.setObjectName("groupBox")
        self.horizontalLayout_3 = QtGui.QHBoxLayout(self.groupBox)
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.verticalLayout_2 = QtGui.QVBoxLayout()
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.horizontalLayout_4 = QtGui.QHBoxLayout()
        self.horizontalLayout_4.setObjectName("horizontalLayout_4")
        spacerItem6 = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.horizontalLayout_4.addItem(spacerItem6)
        self.jim_peak1 = QtGui.QSpinBox(self.groupBox)
        self.jim_peak1.setMaximum(303)
        self.jim_peak1.setObjectName("jim_peak1")
        self.horizontalLayout_4.addWidget(self.jim_peak1)
        self.verticalLayout_2.addLayout(self.horizontalLayout_4)
        self.jim_slider_peak1 = QtGui.QSlider(self.groupBox)
        self.jim_slider_peak1.setMaximum(303)
        self.jim_slider_peak1.setOrientation(QtCore.Qt.Horizontal)
        self.jim_slider_peak1.setObjectName("jim_slider_peak1")
        self.verticalLayout_2.addWidget(self.jim_slider_peak1)
        self.horizontalLayout_3.addLayout(self.verticalLayout_2)
        self.verticalLayout_3 = QtGui.QVBoxLayout()
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.horizontalLayout_5 = QtGui.QHBoxLayout()
        self.horizontalLayout_5.setObjectName("horizontalLayout_5")
        self.jim_peak2 = QtGui.QSpinBox(self.groupBox)
        self.jim_peak2.setMaximum(303)
        self.jim_peak2.setObjectName("jim_peak2")
        self.horizontalLayout_5.addWidget(self.jim_peak2)
        spacerItem7 = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.horizontalLayout_5.addItem(spacerItem7)
        self.verticalLayout_3.addLayout(self.horizontalLayout_5)
        self.jim_slider_peak2 = QtGui.QSlider(self.groupBox)
        self.jim_slider_peak2.setMaximum(303)
        self.jim_slider_peak2.setOrientation(QtCore.Qt.Horizontal)
        self.jim_slider_peak2.setObjectName("jim_slider_peak2")
        self.verticalLayout_3.addWidget(self.jim_slider_peak2)
        self.horizontalLayout_3.addLayout(self.verticalLayout_3)
        self.verticalLayout.addWidget(self.groupBox)
        self.groupBox_2 = QtGui.QGroupBox(self.tab_2)
        self.groupBox_2.setObjectName("groupBox_2")
        self.horizontalLayout_6 = QtGui.QHBoxLayout(self.groupBox_2)
        self.horizontalLayout_6.setObjectName("horizontalLayout_6")
        self.verticalLayout_4 = QtGui.QVBoxLayout()
        self.verticalLayout_4.setObjectName("verticalLayout_4")
        self.horizontalLayout_7 = QtGui.QHBoxLayout()
        self.horizontalLayout_7.setObjectName("horizontalLayout_7")
        spacerItem8 = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.horizontalLayout_7.addItem(spacerItem8)
        self.jim_back1 = QtGui.QSpinBox(self.groupBox_2)
        self.jim_back1.setMaximum(303)
        self.jim_back1.setObjectName("jim_back1")
        self.horizontalLayout_7.addWidget(self.jim_back1)
        spacerItem9 = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.horizontalLayout_7.addItem(spacerItem9)
        self.verticalLayout_4.addLayout(self.horizontalLayout_7)
        self.jim_slider_back1 = QtGui.QSlider(self.groupBox_2)
        self.jim_slider_back1.setMaximum(303)
        self.jim_slider_back1.setOrientation(QtCore.Qt.Horizontal)
        self.jim_slider_back1.setObjectName("jim_slider_back1")
        self.verticalLayout_4.addWidget(self.jim_slider_back1)
        self.horizontalLayout_6.addLayout(self.verticalLayout_4)
        self.verticalLayout_5 = QtGui.QVBoxLayout()
        self.verticalLayout_5.setObjectName("verticalLayout_5")
        self.horizontalLayout_8 = QtGui.QHBoxLayout()
        self.horizontalLayout_8.setObjectName("horizontalLayout_8")
        spacerItem10 = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.horizontalLayout_8.addItem(spacerItem10)
        self.jim_back2 = QtGui.QSpinBox(self.groupBox_2)
        self.jim_back2.setMaximum(303)
        self.jim_back2.setObjectName("jim_back2")
        self.horizontalLayout_8.addWidget(self.jim_back2)
        spacerItem11 = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.horizontalLayout_8.addItem(spacerItem11)
        self.verticalLayout_5.addLayout(self.horizontalLayout_8)
        self.jim_slider_back2 = QtGui.QSlider(self.groupBox_2)
        self.jim_slider_back2.setMaximum(303)
        self.jim_slider_back2.setOrientation(QtCore.Qt.Horizontal)
        self.jim_slider_back2.setObjectName("jim_slider_back2")
        self.verticalLayout_5.addWidget(self.jim_slider_back2)
        self.horizontalLayout_6.addLayout(self.verticalLayout_5)
        self.verticalLayout.addWidget(self.groupBox_2)
        self.tabWidget.addTab(self.tab_2, "")
        self.horizontalLayout_2.addWidget(self.tabWidget)

        self.retranslateUi(Dialog)
        self.tabWidget.setCurrentIndex(1)
        QtCore.QObject.connect(self.jim_peak1, QtCore.SIGNAL("valueChanged(int)"), Dialog.jim_peak1_spinbox_signal)
        QtCore.QObject.connect(self.john_peak1, QtCore.SIGNAL("valueChanged(int)"), Dialog.john_peak1_spinbox_signal)
        QtCore.QObject.connect(self.jim_slider_peak1, QtCore.SIGNAL("valueChanged(int)"), Dialog.jim_peak1_slider_signal)
        QtCore.QObject.connect(self.john_slider_peak1, QtCore.SIGNAL("valueChanged(int)"), Dialog.john_peak1_slider_signal)
        QtCore.QObject.connect(self.jim_slider_peak2, QtCore.SIGNAL("valueChanged(int)"), Dialog.jim_peak2_slider_signal)
        QtCore.QObject.connect(self.jim_peak2, QtCore.SIGNAL("valueChanged(int)"), Dialog.jim_peak2_spinbox_signal)
        QtCore.QObject.connect(self.john_slider_peak2, QtCore.SIGNAL("valueChanged(int)"), Dialog.john_peak2_slider_signal)
        QtCore.QObject.connect(self.john_peak2, QtCore.SIGNAL("valueChanged(int)"), Dialog.john_peak2_spinbox_signal)
        QtCore.QObject.connect(self.jim_back1, QtCore.SIGNAL("valueChanged(int)"), Dialog.jim_back1_spinbox_signal)
        QtCore.QObject.connect(self.john_back1, QtCore.SIGNAL("valueChanged(int)"), Dialog.john_back1_spinbox_signal)
        QtCore.QObject.connect(self.jim_slider_back1, QtCore.SIGNAL("valueChanged(int)"), Dialog.jim_back1_slider_signal)
        QtCore.QObject.connect(self.john_slider_back1, QtCore.SIGNAL("valueChanged(int)"), Dialog.john_back1_slider_signal)
        QtCore.QObject.connect(self.jim_back2, QtCore.SIGNAL("valueChanged(int)"), Dialog.jim_back2_spinbox_signal)
        QtCore.QObject.connect(self.john_back2, QtCore.SIGNAL("valueChanged(int)"), Dialog.john_back2_spinbox_signal)
        QtCore.QObject.connect(self.jim_slider_back2, QtCore.SIGNAL("valueChanged(int)"), Dialog.jim_back2_slider_signal)
        QtCore.QObject.connect(self.john_slider_back2, QtCore.SIGNAL("valueChanged(int)"), Dialog.john_back2_slider_signal)
        QtCore.QMetaObject.connectSlotsByName(Dialog)

    def retranslateUi(self, Dialog):
        Dialog.setWindowTitle(QtGui.QApplication.translate("Dialog", "Dialog", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox_4.setTitle(QtGui.QApplication.translate("Dialog", "PEAK", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox_3.setTitle(QtGui.QApplication.translate("Dialog", "BACKGROUND", None, QtGui.QApplication.UnicodeUTF8))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab), QtGui.QApplication.translate("Dialog", "John", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox.setTitle(QtGui.QApplication.translate("Dialog", "PEAK", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox_2.setTitle(QtGui.QApplication.translate("Dialog", "BACKGROUND", None, QtGui.QApplication.UnicodeUTF8))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_2), QtGui.QApplication.translate("Dialog", "Jim", None, QtGui.QApplication.UnicodeUTF8))

from .mplwidget import MPLWidget
import icons_rc
