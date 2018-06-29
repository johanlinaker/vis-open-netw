from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import threading
import argparse
import urllib.parse as urlparse

import pandas as pd
import networkx as nx
from perceval.backends.core import gerrit as percGerrit

import json
import os

from datetime import datetime
import urllib

import py2neo

neo4jLoc = "http://neo4j:lund101@localhost:7474/db/data/"

perceval = percGerrit.Gerrit('gerrit.opnfv.org', 'user')
issues = perceval.fetch(from_date=datetime(2018, 5, 1, 0, 0))

#buf = '{\n\"items\": ['
#first = True
#for issue in issues:
#    if not first:
#        buf += ','
#    first = False
#    buf += json.dumps(issue['data'])
#buf += ']\n}'

num = 0
for item in issues:
    if num < 1:
        buf = json.dumps(item['data'])
        print(buf)
    num = num + 1
