from PyQt4.QtGui import QDialog, QPalette, QTableWidgetItem, QCheckBox, QFileDialog, QMessageBox, QPushButton, QPixmap, QIcon
from PyQt4.QtCore import Qt, QSize
from metadata_finder_interface import Ui_Dialog as UiDialog
from mantid.simpleapi import *
from run_sequence_breaker import RunSequenceBreaker
from decorators import waiting_effects
import utilities
import os
import time
import nexus_utilities
import numpy as np

class MetadataFinder(QDialog):
	
	_open_instances = []
	main_gui = None

	list_metadata_selected = []
	list_nxs = []
	list_filename = []
	list_runs = []
	
	list_values = []
	list_keys = []
	
	WARNING_NBR_FILES = 10
	
	first_load = True
	
	def __init__(cls, main_gui, parent=None):
		cls.main_gui = main_gui
		
		QDialog.__init__(cls, parent=parent)
		cls.setWindowModality(False)
		cls._open_instances.append(cls)
		cls.ui = UiDialog()
		cls.ui.setupUi(cls)
		
		cls.initGui()
		
	def initList(cls):
		cls.list_runs = []
		cls.list_filename= []
		cls.list_nxs = []
	
	def initGui(cls):
		cls.ui.inputErrorLabel.setVisible(False)
		palette = QPalette()
		palette.setColor(QPalette.Foreground, Qt.red)
		cls.ui.inputErrorLabel.setPalette(palette)
		
		cls.ui.saveAsciiButton.setVisible(False) #as long as issue with routine not fixed
		
		cls.ui.configureTable.setColumnWidth(0,70)
		cls.ui.configureTable.setColumnWidth(1,300)
		cls.ui.configureTable.setColumnWidth(2,300)
		cls.ui.configureTable.setColumnWidth(3,300)
		
		magIcon = QPixmap('../icons/magnifier.png')
		cls.ui.searchLabel.setPixmap(magIcon)
		clearIcon = QIcon('../icons/clear.png')
		cls.ui.clearButton.setIcon(clearIcon)
		sz = QSize(15,15)
		cls.ui.clearButton.setIconSize(sz)
		#cls.ui.clearButton.setVisible(False)
		#cls.ui.searchLabel.setVisible(False)
		#cls.ui.searchLineEdit.setVisible(False)
		
	def initListMetadata(cls):
		_nxs = cls.list_nxs[0]
		mt_run = _nxs.getRun()
		cls.list_keys = mt_run.keys()
		sz = len(cls.list_keys)
		cls.list_values = np.zeros(sz, dtype=bool)

	def searchLineEditLive(cls, txt):
		cls.populateconfigureTable()
		cls.list_metadata_selected = cls.getNewListMetadataSelected()
		cls.loadAndPopulateMetadataTable()

	def searchLineEditClear(cls):
		cls.ui.searchLineEdit.setText('')
		cls.populateconfigureTable()

	def retrieveListMetadataPreviouslySelected(cls):
		from quicknxs.config import metadataSelected
		metadataSelected.switch_config('listMetadata')
		listMetadataSelected = metadataSelected.metadata_list
		cls.list_metadata_selected = listMetadataSelected
		metadataSelected.switch_config('default')
		_list_values = cls.list_values
		for idx, val in enumerate(cls.list_keys):
			if val in listMetadataSelected:
				_list_values[idx] = True
			else:
				_list_values[idx] = False
		cls.list_values = _list_values
		
	def clearMetadataTable(cls):
		_meta_table = cls.ui.metadataTable
		nbr_row = _meta_table.rowCount()
		for i in range(nbr_row):
			_meta_table.removeRow(0)
		nbr_column = _meta_table.columnCount()
		if nbr_column > 2:
			for j in range(nbr_column,1,-1):
				_meta_table.removeColumn(j)
		_meta_table.show()

	def clearConfigureTable(cls):
		_config_table = cls.ui.configureTable
		nbr_row = _config_table.rowCount()
		for i in range(nbr_row):
			_config_table.removeRow(0)
		_config_table.show()
			
	@waiting_effects
	def runNumberEditEvent(cls):
		cls.initList()
		cls.clearMetadataTable()
		cls.loadNxs()
		cls.populateMetadataTable()
		cls.populateconfigureTable()
		cls.ui.runNumberEdit.setText("")
		cls.updateGUI()
		cls.list_metadata_selected = cls.getNewListMetadataSelected()
		cls.loadAndPopulateMetadataTable()
		
	def updateGUI(cls):
		if cls.list_nxs != []:
			config_widget_status = True
		else:
			config_widget_status = False
		cls.ui.unselectAll.setEnabled(config_widget_status)
		cls.ui.exportConfiguration.setEnabled(config_widget_status)
		cls.ui.importConfiguration.setEnabled(config_widget_status)
		cls.ui.saveAsciiButton.setEnabled(config_widget_status)
		
	def populateconfigureTable(cls):
		if cls.ui.inputErrorLabel.isVisible():
			return
		if cls.list_filename == []:
			return
		cls.clearConfigureTable()
		#_filename = cls.list_filename[0]
		#nxs = LoadEventNexus(Filename=_filename)
		
		nxs = cls.list_nxs[0]
		if cls.first_load:
			cls.first_load = False
			#mt_run = nxs.getRun()
			#cls.list_keys = mt_run.keys()
			cls.initListMetadata()
			cls.retrieveListMetadataPreviouslySelected()

		list_keys = cls.list_keys
		list_values = cls.list_values
		search_string = cls.ui.searchLineEdit.text().lower()

		_index = 0
		for _key in list_keys:
			_name = _key
			if (search_string.strip() != '') and (not(search_string in _name.lower())):
				continue
			
			cls.ui.configureTable.insertRow(_index)

			_yesNo = QCheckBox()
			_id = list_keys.index(_name)
			_value = list_values[_id]
			_yesNo.setChecked(_value)
			_yesNo.setText('')
			_yesNo.stateChanged.connect(cls.configTableEdited)
			cls.ui.configureTable.setCellWidget(_index, 0, _yesNo)

			_nameItem = QTableWidgetItem(_name)
			cls.ui.configureTable.setItem(_index, 1, _nameItem)
			
			[value, units] = cls.retrieveValueUnits(nxs.getRun(),_name)
			_valueItem = QTableWidgetItem(value)
			cls.ui.configureTable.setItem(_index, 2, _valueItem)
			_unitsItem = QTableWidgetItem(units)
			cls.ui.configureTable.setItem(_index, 3, _unitsItem)
			
			_index += 1
			
	def configTableEdited(cls, value):
		_list_keys = cls.list_keys
		_list_values = cls.list_values
		_config_table = cls.ui.configureTable
		nbr_row = _config_table.rowCount()
		_list_metadata_selected = []
		for r in range(nbr_row):
			_is_selected = _config_table.cellWidget(r,0).isChecked()
			_name = _config_table.item(r,1).text()
			if _is_selected:
				_list_metadata_selected.append(_name)
			_index = _list_keys.index(_name)
			_list_values[_index] = _is_selected

		cls.list_values = _list_values
		cls.list_metadata_selected = _list_metadata_selected
			
	def retrieveValueUnits(cls, mt_run, _name):
		_name = str(_name)
		_value = mt_run.getProperty(_name).value
		if isinstance(_value, float):
			_value = str(_value)
		elif len(_value) == 1:
			_value = str(_value)
		elif type(_value) == type(""):
			_value = _value
		else:
			_value = '[' + str(_value[0]) + ',...]' + '-> (' + str(len(_value)) + ' entries)'
		_units = mt_run.getProperty(_name).units
		return [_value, _units]

	def loadAndPopulateMetadataTable(cls):
		cls.loadNxs()
		cls.populateMetadataTable()
		
	def loadNxs(cls):
		cls.clearMetadataTable()
		run_sequence = cls.ui.runNumberEdit.text()
		oListRuns = RunSequenceBreaker(run_sequence)
		_list_runs = oListRuns.getFinalList()
		if len(_list_runs) > cls.WARNING_NBR_FILES:
			msgBox = QMessageBox()
			_str = "Program is about to load " + str(len(_list_runs)) + " files. Do you want to continue ?" 	                                                              
			msgBox.setText(_str)
			msgBox.addButton(QPushButton('NO'), QMessageBox.NoRole)
			msgBox.addButton(QPushButton('YES'), QMessageBox.YesRole)
			ret = msgBox.exec_()
			if ret == 0:
				cls.ui.inputErrorLabel.setVisible(False)
				return

		if _list_runs[0] == -1:
			if cls.list_nxs == []:
				return
			else:
				_list_runs = cls.list_runs
				_list_nxs = cls.list_nxs
				_list_filename = cls.list_filename
		
		elif _list_runs[0] == -2:
			cls.ui.inputErrorLabel.setVisible(True)
			return
		
		else:
			cls.list_runs = _list_runs
			cls.list_filename = []
			cls.list_nxs = []
			for _runs in _list_runs:
				try:
					_filename = nexus_utilities.findNeXusFullPath(_runs)
				except:
					cls.ui.inputErrorLabel.setVisible(True)					
					return
				cls.list_filename.append(_filename)
				randomString = utilities.generate_random_workspace_name()
				_nxs = LoadEventNexus(Filename=_filename, OutputWorkspace=randomString, MetaDataOnly=True)							
				cls.list_nxs.append(_nxs)
		
		cls.ui.inputErrorLabel.setVisible(False)
		list_metadata_selected = cls.list_metadata_selected
		
		_header = ['Run #','IPTS']
		for name in list_metadata_selected:
			cls.ui.metadataTable.insertColumn(2)
			_header.append(name)
		cls.ui.metadataTable.setHorizontalHeaderLabels(_header)
		list_nxs = cls.list_nxs
			
	def populateMetadataTable(cls):
		list_metadata_selected = cls.list_metadata_selected
		
		_index = 0
		for i in range(len(cls.list_nxs)):
			cls.ui.metadataTable.insertRow(_index)
			
			_nxs = cls.list_nxs[i]
			mt_run = _nxs.getRun()
			
			_runs = cls.list_runs[i]
			_runItem = QTableWidgetItem(str(_runs))
			cls.ui.metadataTable.setItem(_index, 0, _runItem)

			_filename = cls.list_filename[i]
			_ipts = cls.getIPTS(_filename)
			_iptsItem = QTableWidgetItem(_ipts)
			cls.ui.metadataTable.setItem(_index, 1, _iptsItem)
			
			column_index = 0			
			for name in list_metadata_selected:
				[value,units] = cls.retrieveValueUnits(mt_run, name)
				_str = str(value) + ' ' + str(units)
				_item = QTableWidgetItem(_str)
				cls.ui.metadataTable.setItem(_index, 2+column_index, _item)
				column_index += 1
			
			_index += 1
			
	def unselectAll(cls):
		_config_table = cls.ui.configureTable
		nbr_row = _config_table.rowCount()
		for r in range(nbr_row):
			_name = cls.ui.configureTable.item(r,1).text()
			_yesNo = QCheckBox()
			_yesNo.setText('')
			cls.ui.configureTable.setCellWidget(r, 0, _yesNo)
	
	def closeEvent(cls, event=None):
		cls.saveListMetadataSelected()	
		
	def saveListMetadataSelected(cls):
		_listMetadata = cls.list_metadata_selected
		from quicknxs.config import metadataSelected
		metadataSelected.switch_config('listMetadata')
		metadataSelected.metadata_list = _listMetadata
		metadataSelected.switch_config('default')
			
	def importConfiguration(cls):
		_filter = u"Metadata Configuration (*_metadata.cfg);; All (*.*)"
		_default_path = cls.main_gui.path_config
		filename = QFileDialog.getOpenFileName(cls, u'Import Metadata Configuration',
		                                       directory=_default_path,
		                                       filter=(_filter))
		if filename == '':
			return
		
		data = utilities.import_ascii_file(filename)
		cls.list_metadata_selected = data
		cls.populateconfigureTable()
	
	def exportConfiguration(cls):
		_filter = u"Metadata Configuration (*_metadata.cfg);; All (*.*)"
		_date = time.strftime("%d_%m_%Y")
		_default_name = cls.main_gui.path_config + '/' + _date + '_metadata.cfg'
		filename = QFileDialog.getSaveFileName(cls, u'Export Metadata Configuration',
	                                               _default_name,
	                                               filter = (_filter))
		if filename == '':
			return
		
		cls.main_gui.path_config = os.path.dirname(filename)
		
		list_metadata_selected = cls.list_metadata_selected
		text = []
		for _name in list_metadata_selected:
			text.append(_name)
			
		utilities.write_ascii_file(filename, text)
	
	def getIPTS(cls, filename):
		parse_path = filename.split('/')
		return parse_path[3]
	
	def userChangedTab(cls, int):
		#search_label_visible = True
		if int ==0: #metadata
			cls.list_metadata_selected = cls.getNewListMetadataSelected()
			cls.loadAndPopulateMetadataTable()
			#search_label_visible = False
		#cls.ui.searchLabel.setVisible(search_label_visible)
		#cls.ui.searchLineEdit.setVisible(search_label_visible)
		#cls.ui.clearButton.setVisible(search_label_visible)
			
	def getNewListMetadataSelected(cls):
		_config_table = cls.ui.configureTable
		nbr_row = _config_table.rowCount()
		if nbr_row == 0:
			return cls.list_metadata_selected
		_list_metadata_selected = []
		for r in range(nbr_row):
			_is_selected = _config_table.cellWidget(r,0).isChecked()
			if _is_selected:
				_name = _config_table.item(r,1).text()
				_list_metadata_selected.append(_name)
		return _list_metadata_selected
		
	def saveMetadataListAsAsciiFile(cls):
		if cls.list_runs == []:
			return
		_filter = u'List Metadata (*_metadata.txt);;All(*.*)'
		_run_number = str(cls.list_runs[0])
		_default_name = cls.main_gui.path_ascii + '/' + _run_number + '_metadata.txt'
		filename = QFileDialog.getSaveFileName(cls, u'Save Metadata into ASCII',
	                                               _default_name,
	                                               filter=_filter)
		if filename == '':
			return
	
		cls.main_gui.path_config = os.path.dirname(filename)
		
		text = ['# Metadata Selected for run ' + _run_number]
		text.append('#Name - Value - Units')
		
		_metadata_table = cls.ui.metadataTable
		nbr_row = _metadata_table.rowCount()
		for r in range(nbr_row):
			_line = _metadata_table.item(r,0).text() + ' ' + str(_metadata_table.item(r,1).text()) + ' ' + 	str(_metadata_table.item(r,2).text())
			text.append(_line)
		utilities.write_ascii_file(filename, text)
	
	