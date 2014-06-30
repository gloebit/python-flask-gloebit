import os
import sys
import socket
import logging

logging.basicConfig (stream=sys.stderr)

top=os.path.abspath (os.path.dirname (__file__))
sys.path.insert (0, top)
sys.path.insert (0, top+'/Lib')

from GloebitExample import app as application
