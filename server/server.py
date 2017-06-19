from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import threading
import argparse
import urllib.parse as urlparse

import pandas as pd
import networkx as nx
from perceval.backends.core import jira as percJira

import json

from datetime import datetime
import urllib

import py2neo

def populateNeoDB(graph, url, project, fromDateTime):
    # Connect to graph and add constraints.
    graph.delete_all()
    graph.run("CREATE CONSTRAINT ON (u:User) ASSERT u.key IS UNIQUE;")

    perceval = percJira.Jira(url, project=project)
    issues = perceval.fetch(from_date=fromDateTime)

    buf = '{\n\"items\": ['
    first = True
    for issue in issues:
        if not first:
            buf += ','
        first = False
        buf += json.dumps(issue['data'])
    buf += ']\n}'


    # Build query - This is JIRA-backend-specific
    query = """
            WITH {json} as data
            UNWIND data.items as i
            MERGE (issue:Issue {id:i.id}) ON CREATE
              SET issue.key = i.key, issue.type = i.fields.issuetype.name, issue.resolutionDate = i.fields.resolutiondate, issue.updateDate = i.fields.updated, issue.createDate = i.fields.created
            
            FOREACH (comm IN i.fields.comment.comments |
                MERGE (comment:Comment {id: comm.id}) ON CREATE SET comment.author = comm.author.key, comment.body = comm.body
                MERGE (comment)-[:ON]->(issue)
                MERGE (author:User {key: comm.author.key}) ON CREATE SET author.name = comm.author.name, author.displayName = comm.author.displayName
                MERGE (author)-[:CREATED]->(comment)
            )
                """

    # Send Cypher query.
    graph.run(query, parameters={"json": json.loads(buf)})

# Set what organization the user is in according to data in orgData
def setOrgs(graph, orgData):
    for user in orgData:
        query = "MATCH (n:User) WHERE n.key = '" + user.decode("utf-8") + "' SET n.organization = '" + orgData[user][0].decode("utf-8") + "'"

        graph.run(query)

    query = """
    MATCH (n:User) WHERE n.organization IS NULL
    SET n.organization = 'undefined'
    """

    graph.run(query)


def readDB(graph, issueTypes, creationFromDate = None, creationToDate = None, resolutionFromDate = None, resolutionToDate = None, unresolved = True):
    params = {}
    # Nbr of comments per user and issue
    # author | issueId | anchor | nbrOfComments
    query = """MATCH (n:Comment)-[r:ON]->(i:Issue) """

    query = query + """ WHERE i.type IN {issueTypes} """
    params['issueTypes'] = issueTypes

    if(creationFromDate is not None):
        query = query + """ AND i.createDate >= {creationFromDate} """
        params['creationFromDate'] = creationFromDate
    if(creationToDate is not None):
        query = query + """ AND i.createDate < {creationToDate} """
        params['creationToDate'] = creationToDate

    firstResolutionFilter = True
    if (resolutionFromDate is not None or resolutionToDate is not None):
        query = query + """ AND ( """

        if (resolutionFromDate is not None):
            query = query + """ i.resolutionDate >= {resolutionFromDate} """
            params['resolutionFromDate'] = resolutionFromDate
            firstResolutionFilter = False

        if (resolutionToDate is not None):
            if not firstResolutionFilter:
                query = query + """ AND """
            query = query + """ i.resolutionDate < {resolutionToDate} """
            params['resolutionToDate'] = resolutionToDate
            firstResolutionFilter = False

        query = query + """ ) """
    if unresolved == True:
        if not firstResolutionFilter:
            query = query + """ OR """
        else:
            query = query + """ AND """
        query = query + """ i.resolutionDate IS NULL """

    query = query + """ RETURN n.author AS author, i.id AS issueId, i.key AS anchor, count(r) AS nbrOfComments"""
    issueData = pd.DataFrame(graph.data(query, parameters=params))

    # Gives total number of comments per issue
    # issueId | totNbrOfComments
    query="""MATCH (n:Comment)-[r:ON]->(i:Issue) RETURN i.id AS issueId, count(r) AS totNbrOfComments"""

    totCommentsPerIssue = pd.DataFrame(graph.data(query))

    # Organizational affiliation per username
    query = """MATCH (n:User) RETURN n.key AS author, n.organization AS organization"""

    orgData = pd.DataFrame(graph.data(query))

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
                                       'issueId',
                                       'totNbrOfComments']).sum().reset_index()

    # issueData.to_csv("01_dbOutput.csv")

    return issueData

def calcWeights(issueData, fileName):

    # Add collaborators and merge on common issueId
    collaborators = pd.DataFrame({'issueId': issueData['issueId'],
                                 'collabOrganization': issueData['organization']})

    issueData = pd.merge(issueData, collaborators, how="outer", on="issueId")
    issueData = issueData.drop('issueId', axis=1)

    # Aggregate over general organizational collaboration instead of per issue
    issueData = issueData.groupby(['organization',
                                   'collabOrganization']).sum().reset_index()

    issueData['weight'] = issueData['nbrOfComments'] / issueData['totNbrOfComments']

    issueData['weight'] = issueData['weight'].fillna(0)

    edges = issueData.copy()
    edges.rename(columns={"organization": "from",
                                "collabOrganization": "to",
                                "weight": "label"}, inplace=True)

    edges.to_json("Data/" + fileName + ".json", "records")

    return issueData

def genNetwork(issueData, fileName):

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

    centralityData.to_json("Data/" + fileName + "_metrics.json", "records")

    return centralityData

class HTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        graph = py2neo.Graph("http://neo4j:lund101@localhost:7474/db/data/")

        parsedUrl = urlparse.urlparse(self.path)
        splitPath = parsedUrl.path.lstrip("/").split("/")
        parsedQuery = urlparse.parse_qs(parsedUrl.query)
        keys = parsedQuery.keys()

        # Send Sir Perceval on a quest to populate the Neo4j db
        if(len(splitPath) == 2 and splitPath[0] == 'quest'):
            populateNeoDB(graph, urllib.parse.unquote(splitPath[1]), urllib.parse.unquote(parsedQuery['project'][0]), datetime.strptime(urllib.parse.unquote(parsedQuery['fromDate'][0]), '%m/%d/%Y')) # may need to decode splitPath[1], fromDate
            self.send_response(200)
            self.send_header('Access-Control-Allow-Credentials', 'true')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(bytes('', 'UTF-8')) # may not be needed - just need an OK
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Credentials', 'true')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            if(splitPath[0] == "issueTypes"):
                query = "MATCH (n:Issue) RETURN DISTINCT n.type AS type"
                issueTypes = graph.run(query)

                self.wfile.write(bytes(json.dumps(issueTypes.data()), 'UTF-8'))
            elif(splitPath[0] == "dates"):
                query = "MATCH (n:Issue) RETURN MIN(n.createDate) AS creationMin, MAX(n.createDate) AS creationMax, MIN(n.resolutionDate) AS resolutionMin, MAX(n.resolutionDate) AS resolutionMax"
                dates = graph.run(query)

                self.wfile.write(bytes(json.dumps(dates.data()), 'UTF-8'))
            elif(splitPath[0] == "users"):
                query = "MATCH (n:User) RETURN n.key AS username, n.displayName AS displayName, n.organization as organization"
                users = graph.run(query)

                self.wfile.write(bytes(json.dumps(users.data()), 'UTF-8'))
            else:
                if (len(keys) != 0 and 'issueTypes' in keys): # if there are no issueTypes then there is no response
                    issueTypes = parsedQuery['issueTypes'][0].split()
                    creationFromDate = parsedQuery['creationFromDate'][0] if 'creationFromDate' in keys else None
                    creationToDate = parsedQuery['creationToDate'][0] if 'creationToDate' in keys else None
                    resolutionFromDate = parsedQuery['resolutionFromDate'][0] if 'resolutionFromDate' in keys else None
                    resolutionToDate = parsedQuery['resolutionToDate'][0] if 'resolutionToDate' in keys else None
                    unresolved = parsedQuery['unResolved'][0] if 'unResolved' in keys else None
                    res = readDB(graph, issueTypes, creationFromDate, creationToDate, resolutionFromDate, resolutionToDate, True if unresolved == "true" else False)
                    res = calcWeights(res, parsedQuery['url'][0])
                    res = genNetwork(res, parsedQuery['url'][0])

                    try:
                        file = open("Data/" + splitPath[0] + ".json")
                    except IOError:
                        self.send_error(404, self.path + " does not exist.")
                        return
                    self.wfile.write(bytes(file.read(), 'UTF-8'))
                else:
                    self.wfile.write(bytes(' ', 'UTF-8'))
        return

    def do_POST(self):
        graph = py2neo.Graph("http://neo4j:lund101@localhost:7474/db/data/")

        parsedUrl = urlparse.urlparse(self.path)
        splitPath = parsedUrl.path.lstrip("/").split("/")

        if(splitPath[0] == "usersToOrgs"):
            orgData = urlparse.parse_qs(self.rfile.read(int(self.headers.get('content-length'))))

            setOrgs(graph, orgData)


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