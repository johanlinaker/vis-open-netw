from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import threading
import argparse

import pandas as pd
import networkx as nx
# import matplotlib.pyplot as plt
import pymysql

import csv
import json
import os

def readDB(db):
    pymysql.install_as_MySQLdb()
    db = pymysql.connect(host = "vm23.cs.lth.se",
                         user = "kylec",
                         passwd = "oc12UnBjNT",
                         db = db)

    cur = db.cursor()

    # Nbr of comments per user and issue
    # author | issueId | anchor | nbrOfComments
    query = """SELECT
                c.author AS author,
                c.issueId AS issueId,
                i.anchor AS anchor,
                COUNT(*) AS nbrOfComments
            FROM
                jira_issue_comments c,
                jira_issues i
            WHERE
                c.issueId = i.id
            GROUP BY
                c.author, c.issueId
            ORDER BY
                c.author"""

    issueData = pd.read_sql_query(query, db)

    # Issue id:s per release
    # releaseData = pd.read_csv("releaseData.csv", header=0, sep=",")
    # releaseData = releaseData.where(releaseData['release'] != 'R2.8.0')

    # Gives total number of comments per issue
    # issueId | totNbrOfComments
    query = """SELECT
                issueId,
                COUNT(*)
                AS
                totNbrOfComments
            FROM
                jira_issue_comments
            GROUP BY
                issueId;"""

    totCommentsPerIssue = pd.read_sql_query(query, db)

    # Organizational affiliation per username
    query = """SELECT
                p.username AS author,
                p.organization AS organization,
                o.id AS organizationId
            FROM
                jira_people p,
                jira_organizations o
            WHERE
                p.organization = o.organization;"""

    orgData = pd.read_sql_query(query, db)
    db.close()

    # Add column with total number of comments per issue to issueData
    issueData = pd.merge(issueData, totCommentsPerIssue, how="right", on="issueId")
    #
    # Add column with organizational affiliation
    issueData = pd.merge(issueData, orgData, how="outer", on="author")
    #
    # Remove comments from from QA and Build bots, and rows with missing values
    issueData = issueData[(issueData['author'] != "hudson") & (issueData['author'] != "hadoopqa")]
    issueData = issueData.dropna()

    # Aggregate based on organizational affiliation
    issueData = issueData.groupby(['organization',
                                       'organizationId',
                                       'issueId',
                                       'totNbrOfComments']).sum().reset_index()

    #issueData.to_csv("01_dbOutput.csv")

    return issueData

def calcWeights(issueData):

    # Add collaborators and merge on common issueId
    collaborators = pd.DataFrame({'issueId': issueData['issueId'],
                                 'collabOrganization': issueData['organization'],
                                 'collabOrganizationId': issueData['organizationId']})

    issueData = pd.merge(issueData, collaborators, how="outer", on="issueId")
    issueData = issueData.drop('issueId', axis=1)

    # Aggregate over general organizational collaboration instead of per issue
    issueData = issueData.groupby(['organization',
                                   'organizationId',
                                   'collabOrganization',
                                   'collabOrganizationId']).sum().reset_index()

    issueData['weight'] = issueData['nbrOfComments'] / issueData['totNbrOfComments']

    issueData['weight'] = issueData['weight'].fillna(0)

    edges = issueData.copy()
    edges.rename(columns={"organization": "from",
                                "collabOrganization": "to",
                                "weight": "label"}, inplace=True)

    issueOutputFileName = "02_weightOutput"
    issueOutputFileCSVName = issueOutputFileName + ".csv"
    edges.to_csv(issueOutputFileCSVName)

    with open(issueOutputFileCSVName) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    os.remove(issueOutputFileCSVName)

    with open("Data/" + issueOutputFileName + ".json", 'w') as f:
        json.dump(rows, f)

    return issueData

def genNetwork(issueData):

    netw = nx.from_pandas_dataframe(issueData,
                                    'organization',
                                    'collabOrganization',
                                    'weight')
    # outdegree = nx.out_degree_centrality(netw)
    # indegree = nx.in_degree_centrality(netw)
    degree = nx.degree_centrality(netw)
    betweeness = nx.betweenness_centrality(netw, weight="weight")
    closeness = nx.closeness_centrality(netw, distance="weight")
    eigenvector = nx.eigenvector_centrality(netw)

    # pos = nx.spring_layout(netw)  # positions for all nodes
    #
    # # nodes
    # nx.draw_networkx_nodes(netw, pos, node_size=10)
    #
    # # edges
    # # nx.draw_networkx_edges(netw, pos, edgelist=elarge,
    # #                        width=6)
    # # nx.draw_networkx_edges(netw, pos, edgelist=esmall,
    # #                        width=6, alpha=0.5, edge_color='b', style='dashed')
    #
    # # labels
    # nx.draw_networkx_labels(netw, pos, font_size=10, font_family='sans-serif')
    #
    # plt.axis('off')
    # plt.savefig("weighted_graph.png")  # save as png
    # plt.show()  # display

    centralityData = pd.DataFrame([degree,
                                   betweeness,
                                   closeness,
                                   eigenvector]).T.reset_index()
    centralityData = centralityData.rename(columns={"index": "company",
                                                    0: "degree",
                                                    1: "betweenness",
                                                    2: "closeness",
                                                    3: "eigenvector"})

    centralityData.to_csv("03_centralityOutput.csv")

    centralityOutputFileName = "03_centralityOutput"
    centralityOutputFileCSVName = centralityOutputFileName + ".csv"
    centralityData.to_csv(centralityOutputFileCSVName)

    with open(centralityOutputFileCSVName) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    os.remove(centralityOutputFileCSVName)

    with open("Data/02_weightOutput_metrics.json", 'w') as f:
        json.dump(rows, f)

    return centralityData

class HTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if(self.path == "/potentialFiles"):
            res = readDB("kylec")
            res = calcWeights(res)
            res = genNetwork(res)
            self.send_response(200)
            self.send_header('Access-Control-Allow-Credentials', 'true')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            files = os.listdir("Data")
            self.wfile.write(bytes(str([file for file in files if file[-13:] != "_metrics.json"]), 'UTF-8'))
        else:
            try:
                file = open("Data" + self.path)
            except IOError:
                self.send_error(404, self.path + " does not exist.")
                return

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Credentials', 'true')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(bytes(file.read(), 'UTF-8'))
        return


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True

    def shutdown(self):
        self.socket.close()
        HTTPServer.shutdown(self)


class SimpleHttpServer():
    def __init__(self, ip, port):
        self.server = ThreadedHTTPServer((ip, port), HTTPRequestHandler)

    def start(self):
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()

    def waitForThread(self):
        self.server_thread.join()

    def stop(self):
        self.server.shutdown()
        self.waitForThread()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='HTTP Server')
    parser.add_argument('port', type=int, help='Listening port for HTTP Server')
    parser.add_argument('ip', help='HTTP Server IP')
    args = parser.parse_args()

    server = SimpleHttpServer(args.ip, args.port)
    print('HTTP Server Running...........')
    server.start()
    server.waitForThread()