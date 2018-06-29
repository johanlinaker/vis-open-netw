from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import threading
import argparse
import urllib.parse as urlparse

import pandas as pd
import networkx as nx
from perceval.backends.core import rss as percRSS

import json
import os

from datetime import datetime
import urllib

perceval = percRSS.RSS('https://groups.google.com/forum/feed/repo-discuss/msgs/rss.xml')
issues = perceval.fetch()
num = 0
for item in issues:
    num = num + 1
    print(item['data']['author']+": "+item['data']['summary'])

