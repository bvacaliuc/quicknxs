from mantid.simpleapi import *
from .qreduce import NXSData

class ReductionObject(object):

    # data and norm run number (from GUI main table)
    dataCell = None
    normCell = None

    # data, norm and config from bigTableData Array
    oData = None
    oNorm = None
    oConfig = None
    
    def __init__(self, main_gui, dataCell, normCell, oData, oNorm, oConfig):
        '''
        Initialize the reduction object by 
        setting data and normalization files
        '''
        self.dataCell = dataCell
        self.normCell = normCell
        
        self.oConfig = oConfig

        # if the oData is empty, retrieve info from oConfig
        if oData is None:
            oData = self.populate_data_object(main_gui, oConfig, 'data')
        self.oData = oData
        
        # retrieve norm if user wants norm and if normCell is not empty
        if normCell != '':
            if oNorm is None:
                # make sure the norm flag is on in the config file
                if oConfig.norm_flag:
                    oNorm = self.populate_data_object(main_gui, oConfig, 'norm')
            else: # make sure the flag is ON         
                if not(oNorm.active_data.norm_flag):
                    oNorm = None
                
        self.oNorm = oNorm

    def integrate_over_low_res_range(self):
        '''
        This will integrate over the low resolution range of the data and norm objects
        '''
#        print 'integrate_over_low_res_range'
        data = self.oData.active_data       
#        print 'data: '
#        print '-> data_low_res_flag: %s' %data.data_low_res_flag
        if data.data_low_res_flag:
            from_pixel = data.data_low_res[0]
            to_pixel = data.data_low_res[1]
        else:
            from_pixel = data.low_resolution_range[0]
            to_pixel = data.low_resolution_range[1]
            
#        print '-> from_pixel: %d' % from_pixel
#        print '-> to_pixel: %d' % to_pixel

        Ixyt = data.Ixyt
        print len(Ixyt)
        
        
        if self.oNorm is not None:
            norm = self.oNorm.active_data
        
            print norm.norm_low_res_flag

    def populate_data_object(self, main_gui, oConfig, type):
        '''
        will retrieve all the info from the oConfig table and will populate the oData object
        type is either 'data' or 'norm'
        '''
        
        # check first if we have a full file name already
        if oConfig is not None:
            if type == 'data':
                full_file_name = oConfig.data_full_file_name
                if full_file_name == u'':
                    _run_number = oConfig.data_sets
                    full_file_name = FileFinder.findRuns("REF_L%d" %int(_run_number))[0]
            else:
                if oConfig.norm_flag:
                    full_file_name = oConfig.norm_full_file_name
                    if full_file_name == u'':
                        _run_number = oConfig.norm_sets
                        full_file_name = FileFinder.findRuns("REF_L%d" %int(_run_number))[0]

            event_split_bins = None
            event_split_index = 0
            bin_type = 0
            
            oData = NXSData(full_file_name,
                            bin_type = bin_type,
                            bins = main_gui.ui.eventTofBins.value(),
                            callback = None,
                            event_split_bins = event_split_bins,
                            event_split_index = event_split_index,
                            metadata_config_object = oConfig)
        
            return oData

        return None

class REFLReduction(object):

    # bigTableData = None

    def __init__(cls, main_gui):
        '''
        Initialize the REFL reduction
        '''

        # retrive full data to reduce
        bigTableData = main_gui.bigTableData
        
        # number of reduction process to run
        nbrRow = main_gui.ui.reductionTable.rowCount()
        
        nbrRow = 1 #FIXME
        for row in range(nbrRow):

            dataCell = main_gui.ui.reductionTable.item(row,0).text()
            normCell = main_gui.ui.reductionTable.item(row,6).text()
            
            print 'working with DATA %s and NORM %s' %(dataCell, normCell)
            
            dataObject = bigTableData[row,0]
            normObject = bigTableData[row,1]
            configObject = bigTableData[row,2]
            
            red1 = ReductionObject(main_gui, dataCell, normCell, dataObject, normObject, configObject)
            bigTableData[row,0] = red1.oData
            bigTableData[row,1] = red1.oNorm

            # integrate low res range of data and norm
            red1.integrate_over_low_res_range()
            
            
            











        # put back the object created in the bigTable to speed up next preview / load
        main_gui.bigTableData = bigTableData
        
        
        