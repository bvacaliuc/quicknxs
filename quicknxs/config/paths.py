#-*- coding: utf-8 -*-
'''
Configured path variables.
'''

import os
from getpass import getuser

config_file=''

# define global path variables usable in config strings or other modules
HOME=os.path.expanduser(u'~')
CFG_PATH=os.path.join(HOME, u'.quicknxs')
CFG_FILE=os.path.join(CFG_PATH, u'config.cfg')
USER=getuser()
# path to the quicknxs package
PACKAGE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not os.path.exists(CFG_PATH):
  os.makedirs(CFG_PATH)

results=u'%(HOME)s/results'
export_name=u'%(instrument.NAME)s_{numbers}_{item}_{state}.{type}'
DOC_INDEX=u'%(PACKAGE)s/htmldoc/node3.html'
STATE_FILE=u'%(CFG_PATH)s/run_state.dat'
LOG_FILE=u'%(CFG_PATH)s/debug.log'
GENX_TEMPLATES=u'%(PACKAGE)s/genx_templates'
