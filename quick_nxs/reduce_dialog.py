# -*- coding: utf-8 -*-
#@PydevCodeAnalysisIgnore

# Form implementation generated from reading ui file 'designer/reduce_dialog.ui'
#
# Created: Wed Apr  3 17:47:26 2013
#      by: PyQt4 UI code generator 4.9.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

try:
  _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
  _fromUtf8 = lambda s: s

class Ui_Dialog(object):
  def setupUi(self, Dialog):
    Dialog.setObjectName(_fromUtf8("Dialog"))
    Dialog.resize(400, 438)
    icon = QtGui.QIcon()
    icon.addPixmap(QtGui.QPixmap(_fromUtf8(":/General/logo.png")), QtGui.QIcon.Normal, QtGui.QIcon.Off)
    Dialog.setWindowIcon(icon)
    self.verticalLayout_4 = QtGui.QVBoxLayout(Dialog)
    self.verticalLayout_4.setObjectName(_fromUtf8("verticalLayout_4"))
    self.tabWidget = QtGui.QTabWidget(Dialog)
    self.tabWidget.setDocumentMode(True)
    self.tabWidget.setObjectName(_fromUtf8("tabWidget"))
    self.tab = QtGui.QWidget()
    self.tab.setObjectName(_fromUtf8("tab"))
    self.verticalLayout_2 = QtGui.QVBoxLayout(self.tab)
    self.verticalLayout_2.setMargin(0)
    self.verticalLayout_2.setObjectName(_fromUtf8("verticalLayout_2"))
    self.widget = QtGui.QWidget(self.tab)
    self.widget.setObjectName(_fromUtf8("widget"))
    self.horizontalLayout = QtGui.QHBoxLayout(self.widget)
    self.horizontalLayout.setMargin(0)
    self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
    self.groupBox_2 = QtGui.QGroupBox(self.widget)
    sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Expanding)
    sizePolicy.setHorizontalStretch(0)
    sizePolicy.setVerticalStretch(0)
    sizePolicy.setHeightForWidth(self.groupBox_2.sizePolicy().hasHeightForWidth())
    self.groupBox_2.setSizePolicy(sizePolicy)
    self.groupBox_2.setObjectName(_fromUtf8("groupBox_2"))
    self.verticalLayout = QtGui.QVBoxLayout(self.groupBox_2)
    self.verticalLayout.setObjectName(_fromUtf8("verticalLayout"))
    self.exportSpecular = QtGui.QCheckBox(self.groupBox_2)
    self.exportSpecular.setChecked(True)
    self.exportSpecular.setObjectName(_fromUtf8("exportSpecular"))
    self.verticalLayout.addWidget(self.exportSpecular)
    self.exportTrueSpecular = QtGui.QCheckBox(self.groupBox_2)
    self.exportTrueSpecular.setEnabled(False)
    self.exportTrueSpecular.setObjectName(_fromUtf8("exportTrueSpecular"))
    self.verticalLayout.addWidget(self.exportTrueSpecular)
    self.exportOffSpecular = QtGui.QCheckBox(self.groupBox_2)
    self.exportOffSpecular.setObjectName(_fromUtf8("exportOffSpecular"))
    self.verticalLayout.addWidget(self.exportOffSpecular)
    self.exportOffSpecularSmoothed = QtGui.QCheckBox(self.groupBox_2)
    self.exportOffSpecularSmoothed.setObjectName(_fromUtf8("exportOffSpecularSmoothed"))
    self.verticalLayout.addWidget(self.exportOffSpecularSmoothed)
    self.exportGISANS = QtGui.QCheckBox(self.groupBox_2)
    self.exportGISANS.setObjectName(_fromUtf8("exportGISANS"))
    self.verticalLayout.addWidget(self.exportGISANS)
    self.horizontalLayout.addWidget(self.groupBox_2)
    self.groupBox = QtGui.QGroupBox(self.widget)
    sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Expanding)
    sizePolicy.setHorizontalStretch(0)
    sizePolicy.setVerticalStretch(0)
    sizePolicy.setHeightForWidth(self.groupBox.sizePolicy().hasHeightForWidth())
    self.groupBox.setSizePolicy(sizePolicy)
    self.groupBox.setObjectName(_fromUtf8("groupBox"))
    self.verticalLayout_3 = QtGui.QVBoxLayout(self.groupBox)
    self.verticalLayout_3.setObjectName(_fromUtf8("verticalLayout_3"))
    self.exportUpUp = QtGui.QCheckBox(self.groupBox)
    self.exportUpUp.setChecked(True)
    self.exportUpUp.setObjectName(_fromUtf8("exportUpUp"))
    self.verticalLayout_3.addWidget(self.exportUpUp)
    self.exportDownDown = QtGui.QCheckBox(self.groupBox)
    self.exportDownDown.setChecked(True)
    self.exportDownDown.setObjectName(_fromUtf8("exportDownDown"))
    self.verticalLayout_3.addWidget(self.exportDownDown)
    self.exportUpDown = QtGui.QCheckBox(self.groupBox)
    self.exportUpDown.setChecked(True)
    self.exportUpDown.setObjectName(_fromUtf8("exportUpDown"))
    self.verticalLayout_3.addWidget(self.exportUpDown)
    self.exportDownUp = QtGui.QCheckBox(self.groupBox)
    self.exportDownUp.setChecked(True)
    self.exportDownUp.setObjectName(_fromUtf8("exportDownUp"))
    self.verticalLayout_3.addWidget(self.exportDownUp)
    self.horizontalLayout.addWidget(self.groupBox)
    self.verticalLayout_2.addWidget(self.widget)
    self.groupBox_3 = QtGui.QGroupBox(self.tab)
    self.groupBox_3.setObjectName(_fromUtf8("groupBox_3"))
    self.gridLayout = QtGui.QGridLayout(self.groupBox_3)
    self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
    self.multiAscii = QtGui.QCheckBox(self.groupBox_3)
    self.multiAscii.setChecked(True)
    self.multiAscii.setObjectName(_fromUtf8("multiAscii"))
    self.gridLayout.addWidget(self.multiAscii, 0, 0, 1, 1)
    self.combinedAscii = QtGui.QCheckBox(self.groupBox_3)
    self.combinedAscii.setObjectName(_fromUtf8("combinedAscii"))
    self.gridLayout.addWidget(self.combinedAscii, 0, 1, 1, 1)
    self.matlab = QtGui.QCheckBox(self.groupBox_3)
    self.matlab.setObjectName(_fromUtf8("matlab"))
    self.gridLayout.addWidget(self.matlab, 1, 0, 1, 1)
    self.gnuplot = QtGui.QCheckBox(self.groupBox_3)
    self.gnuplot.setObjectName(_fromUtf8("gnuplot"))
    self.gridLayout.addWidget(self.gnuplot, 2, 0, 1, 1)
    self.plot = QtGui.QCheckBox(self.groupBox_3)
    self.plot.setChecked(True)
    self.plot.setObjectName(_fromUtf8("plot"))
    self.gridLayout.addWidget(self.plot, 2, 1, 1, 1)
    self.genx = QtGui.QCheckBox(self.groupBox_3)
    self.genx.setObjectName(_fromUtf8("genx"))
    self.gridLayout.addWidget(self.genx, 3, 0, 1, 1)
    self.numpy = QtGui.QCheckBox(self.groupBox_3)
    self.numpy.setObjectName(_fromUtf8("numpy"))
    self.gridLayout.addWidget(self.numpy, 1, 1, 1, 1)
    self.verticalLayout_2.addWidget(self.groupBox_3)
    self.horizontalLayout_2 = QtGui.QHBoxLayout()
    self.horizontalLayout_2.setObjectName(_fromUtf8("horizontalLayout_2"))
    self.label = QtGui.QLabel(self.tab)
    self.label.setObjectName(_fromUtf8("label"))
    self.horizontalLayout_2.addWidget(self.label)
    self.directoryEntry = QtGui.QLineEdit(self.tab)
    self.directoryEntry.setObjectName(_fromUtf8("directoryEntry"))
    self.horizontalLayout_2.addWidget(self.directoryEntry)
    self.toolButton = QtGui.QToolButton(self.tab)
    icon = QtGui.QIcon.fromTheme(_fromUtf8("document-open"))
    self.toolButton.setIcon(icon)
    self.toolButton.setObjectName(_fromUtf8("toolButton"))
    self.horizontalLayout_2.addWidget(self.toolButton)
    self.verticalLayout_2.addLayout(self.horizontalLayout_2)
    self.horizontalLayout_3 = QtGui.QHBoxLayout()
    self.horizontalLayout_3.setObjectName(_fromUtf8("horizontalLayout_3"))
    self.label_2 = QtGui.QLabel(self.tab)
    self.label_2.setObjectName(_fromUtf8("label_2"))
    self.horizontalLayout_3.addWidget(self.label_2)
    self.fileNameEntry = QtGui.QLineEdit(self.tab)
    self.fileNameEntry.setObjectName(_fromUtf8("fileNameEntry"))
    self.horizontalLayout_3.addWidget(self.fileNameEntry)
    self.verticalLayout_2.addLayout(self.horizontalLayout_3)
    self.tabWidget.addTab(self.tab, _fromUtf8(""))
    self.tab_2 = QtGui.QWidget()
    self.tab_2.setObjectName(_fromUtf8("tab_2"))
    self.verticalLayout_5 = QtGui.QVBoxLayout(self.tab_2)
    self.verticalLayout_5.setContentsMargins(0, 4, 0, 0)
    self.verticalLayout_5.setObjectName(_fromUtf8("verticalLayout_5"))
    self.gridLayout_3 = QtGui.QGridLayout()
    self.gridLayout_3.setObjectName(_fromUtf8("gridLayout_3"))
    self.emailZIP = QtGui.QCheckBox(self.tab_2)
    self.emailZIP.setChecked(True)
    self.emailZIP.setObjectName(_fromUtf8("emailZIP"))
    self.gridLayout_3.addWidget(self.emailZIP, 0, 2, 1, 1)
    self.emailPlots = QtGui.QRadioButton(self.tab_2)
    self.emailPlots.setObjectName(_fromUtf8("emailPlots"))
    self.gridLayout_3.addWidget(self.emailPlots, 1, 1, 1, 1)
    self.emailAll = QtGui.QRadioButton(self.tab_2)
    self.emailAll.setChecked(True)
    self.emailAll.setObjectName(_fromUtf8("emailAll"))
    self.gridLayout_3.addWidget(self.emailAll, 1, 0, 1, 1)
    self.emailSend = QtGui.QCheckBox(self.tab_2)
    self.emailSend.setObjectName(_fromUtf8("emailSend"))
    self.gridLayout_3.addWidget(self.emailSend, 0, 0, 1, 2)
    self.emailData = QtGui.QRadioButton(self.tab_2)
    self.emailData.setObjectName(_fromUtf8("emailData"))
    self.gridLayout_3.addWidget(self.emailData, 1, 2, 1, 1)
    self.verticalLayout_5.addLayout(self.gridLayout_3)
    self.gridLayout_2 = QtGui.QGridLayout()
    self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
    self.label_4 = QtGui.QLabel(self.tab_2)
    self.label_4.setObjectName(_fromUtf8("label_4"))
    self.gridLayout_2.addWidget(self.label_4, 0, 0, 1, 1)
    self.emailTo = QtGui.QLineEdit(self.tab_2)
    self.emailTo.setObjectName(_fromUtf8("emailTo"))
    self.gridLayout_2.addWidget(self.emailTo, 0, 1, 1, 1)
    self.label_5 = QtGui.QLabel(self.tab_2)
    self.label_5.setObjectName(_fromUtf8("label_5"))
    self.gridLayout_2.addWidget(self.label_5, 1, 0, 1, 1)
    self.emailCC = QtGui.QLineEdit(self.tab_2)
    self.emailCC.setObjectName(_fromUtf8("emailCC"))
    self.gridLayout_2.addWidget(self.emailCC, 1, 1, 1, 1)
    self.label_3 = QtGui.QLabel(self.tab_2)
    self.label_3.setObjectName(_fromUtf8("label_3"))
    self.gridLayout_2.addWidget(self.label_3, 2, 0, 1, 1)
    self.emailSubject = QtGui.QLineEdit(self.tab_2)
    self.emailSubject.setObjectName(_fromUtf8("emailSubject"))
    self.gridLayout_2.addWidget(self.emailSubject, 2, 1, 1, 1)
    self.verticalLayout_5.addLayout(self.gridLayout_2)
    self.label_6 = QtGui.QLabel(self.tab_2)
    self.label_6.setObjectName(_fromUtf8("label_6"))
    self.verticalLayout_5.addWidget(self.label_6)
    self.emailText = QtGui.QPlainTextEdit(self.tab_2)
    self.emailText.setObjectName(_fromUtf8("emailText"))
    self.verticalLayout_5.addWidget(self.emailText)
    self.tabWidget.addTab(self.tab_2, _fromUtf8(""))
    self.verticalLayout_4.addWidget(self.tabWidget)
    self.buttonBox = QtGui.QDialogButtonBox(Dialog)
    self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
    self.buttonBox.setStandardButtons(QtGui.QDialogButtonBox.Cancel|QtGui.QDialogButtonBox.Ok)
    self.buttonBox.setObjectName(_fromUtf8("buttonBox"))
    self.verticalLayout_4.addWidget(self.buttonBox)

    self.retranslateUi(Dialog)
    self.tabWidget.setCurrentIndex(0)
    QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL(_fromUtf8("accepted()")), Dialog.accept)
    QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL(_fromUtf8("rejected()")), Dialog.reject)
    QtCore.QObject.connect(self.toolButton, QtCore.SIGNAL(_fromUtf8("clicked()")), Dialog.changeDir)
    QtCore.QObject.connect(self.gnuplot, QtCore.SIGNAL(_fromUtf8("toggled(bool)")), self.multiAscii.setDisabled)
    QtCore.QMetaObject.connectSlotsByName(Dialog)

  def retranslateUi(self, Dialog):
    Dialog.setWindowTitle(QtGui.QApplication.translate("Dialog", "Reduction Options", None, QtGui.QApplication.UnicodeUTF8))
    self.groupBox_2.setTitle(QtGui.QApplication.translate("Dialog", "Items", None, QtGui.QApplication.UnicodeUTF8))
    self.exportSpecular.setText(QtGui.QApplication.translate("Dialog", "Specular", None, QtGui.QApplication.UnicodeUTF8))
    self.exportTrueSpecular.setText(QtGui.QApplication.translate("Dialog", "True Specular", None, QtGui.QApplication.UnicodeUTF8))
    self.exportOffSpecular.setText(QtGui.QApplication.translate("Dialog", "Off-Specular Raw", None, QtGui.QApplication.UnicodeUTF8))
    self.exportOffSpecularSmoothed.setText(QtGui.QApplication.translate("Dialog", "Off-Specular Smoothed", None, QtGui.QApplication.UnicodeUTF8))
    self.exportGISANS.setText(QtGui.QApplication.translate("Dialog", "GISANS", None, QtGui.QApplication.UnicodeUTF8))
    self.groupBox.setTitle(QtGui.QApplication.translate("Dialog", "States", None, QtGui.QApplication.UnicodeUTF8))
    self.exportUpUp.setText(QtGui.QApplication.translate("Dialog", " X / + / ++/0V", None, QtGui.QApplication.UnicodeUTF8))
    self.exportDownDown.setText(QtGui.QApplication.translate("Dialog", "- / --/+V", None, QtGui.QApplication.UnicodeUTF8))
    self.exportUpDown.setText(QtGui.QApplication.translate("Dialog", "+-/-V", None, QtGui.QApplication.UnicodeUTF8))
    self.exportDownUp.setText(QtGui.QApplication.translate("Dialog", "-+", None, QtGui.QApplication.UnicodeUTF8))
    self.groupBox_3.setTitle(QtGui.QApplication.translate("Dialog", "Output Formats", None, QtGui.QApplication.UnicodeUTF8))
    self.multiAscii.setText(QtGui.QApplication.translate("Dialog", "ASCII for each channel", None, QtGui.QApplication.UnicodeUTF8))
    self.combinedAscii.setText(QtGui.QApplication.translate("Dialog", "Combined ASCII", None, QtGui.QApplication.UnicodeUTF8))
    self.matlab.setText(QtGui.QApplication.translate("Dialog", "Matlab", None, QtGui.QApplication.UnicodeUTF8))
    self.gnuplot.setText(QtGui.QApplication.translate("Dialog", "Gnuplot Script", None, QtGui.QApplication.UnicodeUTF8))
    self.plot.setText(QtGui.QApplication.translate("Dialog", "Show Plot", None, QtGui.QApplication.UnicodeUTF8))
    self.genx.setText(QtGui.QApplication.translate("Dialog", "GenX", None, QtGui.QApplication.UnicodeUTF8))
    self.numpy.setText(QtGui.QApplication.translate("Dialog", "Numpy .npz", None, QtGui.QApplication.UnicodeUTF8))
    self.label.setText(QtGui.QApplication.translate("Dialog", "Directory", None, QtGui.QApplication.UnicodeUTF8))
    self.toolButton.setText(QtGui.QApplication.translate("Dialog", "...", None, QtGui.QApplication.UnicodeUTF8))
    self.label_2.setText(QtGui.QApplication.translate("Dialog", "File Naming", None, QtGui.QApplication.UnicodeUTF8))
    self.fileNameEntry.setText(QtGui.QApplication.translate("Dialog", "REF_M_{numbers}_{item}_{state}.{type}", None, QtGui.QApplication.UnicodeUTF8))
    self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab), QtGui.QApplication.translate("Dialog", "Output Options", None, QtGui.QApplication.UnicodeUTF8))
    self.emailZIP.setText(QtGui.QApplication.translate("Dialog", "ZIP Files", None, QtGui.QApplication.UnicodeUTF8))
    self.emailPlots.setText(QtGui.QApplication.translate("Dialog", "Only Plots", None, QtGui.QApplication.UnicodeUTF8))
    self.emailAll.setText(QtGui.QApplication.translate("Dialog", "All", None, QtGui.QApplication.UnicodeUTF8))
    self.emailSend.setText(QtGui.QApplication.translate("Dialog", "Send email with result files", None, QtGui.QApplication.UnicodeUTF8))
    self.emailData.setText(QtGui.QApplication.translate("Dialog", "Only Data", None, QtGui.QApplication.UnicodeUTF8))
    self.label_4.setText(QtGui.QApplication.translate("Dialog", "To:", None, QtGui.QApplication.UnicodeUTF8))
    self.emailTo.setText(QtGui.QApplication.translate("Dialog", "agf@ornl.gov", None, QtGui.QApplication.UnicodeUTF8))
    self.label_5.setText(QtGui.QApplication.translate("Dialog", "CC:", None, QtGui.QApplication.UnicodeUTF8))
    self.label_3.setText(QtGui.QApplication.translate("Dialog", "Subject:", None, QtGui.QApplication.UnicodeUTF8))
    self.label_6.setText(QtGui.QApplication.translate("Dialog", "Message Text:", None, QtGui.QApplication.UnicodeUTF8))
    self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_2), QtGui.QApplication.translate("Dialog", "Email Results", None, QtGui.QApplication.UnicodeUTF8))

from . import icons_rc
