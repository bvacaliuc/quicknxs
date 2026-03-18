#-*- coding: utf-8 -*-
'''
REF_L (Liquids Reflectometer, beamline 4B) specific values.
'''

config_file=''

NAME='REF_L'
BEAMLINE='4B'

# for the search of files by number
data_base=u'/SNS/REF_L'
BASE_SEARCH=u'*/data/REF_L_%s_'
OLD_BASE_SEARCH=u'*/*/%s/NeXus/REF_L_%s*'
H5_BASE_SEARCH=u'*/nexus/REF_L_%s.nxs.h5'
LIVE_DATA=u'/SNS/REF_L/shared/LiveData/meta_data.xml'
EXTENSION_SCRIPTS=u'/SNS/REF_L/shared/quicknxs_scripts'

# auto-reduction paths
AUTOREFL_LIVE_IMAGE=u'/SNS/REF_L/shared/LiveData/autorefl.png'
AUTOREFL_LIVE_INDEX=u'/SNS/REF_L/shared/LiveData/autorefl_index.txt'
AUTOREFL_RESULT_IMAGE=u'%(origin_path)s/../shared/autoreduce/reflectivity_%(numbers)s.png'
autorefl_folder=u'/SNS/REF_L/shared/autoreduce/'

# background pixels selected on startup
START_BG=(4, 104)

# gives the active area of a detector with SNSdetector_calibration_id as keys
DETECTOR_REGION={
                 # geometry file: (x, y)
                 'REF_L_geom_2011_08_24.xml': ((8, 295) , (8, 246)), # Brookhaven 304x256 detector
                 }

DATABASE_ADDITIONAL_FIELDS=[
                           # field name, daslog entry
                            ('S1W', 'S1HWidth', float),
                            ('S2W', 'S2HWidth', float),
                            ('S3W', 'S3HWidth', float),
                            ('S4W', 'S4HWidth', float),
                            ('S1H', 'S1VHeight', float),
                            ('S2H', 'S2VHeight', float),
                            ('S3H', 'S3VHeight', float),
                            ('S4H', 'S4VHeight', float),
                           ]

database_file=u'/SNS/REF_L/shared/quicknxs_database'

DATABASE_DIRECT_BEAM_COMPARE=[
                              ('s1h', 'S1VHeight', float, 1.0),
                              ('s2h', 'S2VHeight', float, 1.0),
                               ]

# Detector sensitivity correction parameters (None = no polynomial correction available yet)
POLY_CORR_PARAMS=None
