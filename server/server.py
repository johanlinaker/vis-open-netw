from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import threading
import argparse
import urllib.parse as urlparse

import pandas as pd
import networkx as nx
from perceval.backends.core import jira as percJira

import json
import os

from datetime import datetime
import urllib

import py2neo

neo4jLoc = "http://neo4j:lund101@localhost:7474/db/data/"

def cleanDataDir():
    folder = "Data"
    for file in os.listdir(folder):
        filePath = os.path.join(folder, file)
        try:
            if os.path.isfile(filePath):
                os.unlink(filePath)
        except Exception as e:
            print(e)

def scrapeDataToNeo(graph, url, project, fromDateTime):
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

    # Save buffered data for later usage
    fileName = "created=" + datetime.utcnow().strftime("%d-%m-%Y") + "&from=" + fromDateTime.strftime(
            "%d-%m-%Y") + "&project=" + project + "&url=" + urllib.parse.quote(url, safe="")

    path = "Data/Stored/" + fileName
    if os.path.exists(path):
        os.remove(path)
    with open(path, "w+") as storageFile:
        storageFile.write(buf)

    populateNeoDb(graph, buf)

    return fileName

def populateNeoDb(graph, jsonData):
    cleanDataDir()

    graph.delete_all()
    graph.run("CREATE CONSTRAINT ON (u:User) ASSERT u.key IS UNIQUE;")

    # Build query - This is JIRA-backend-specific
    query = """
            WITH {json} as data
            UNWIND data.items as i
            MERGE (issue:Issue {id:i.id}) ON CREATE
              SET issue.key = i.key, issue.type = i.fields.issuetype.name, issue.resolutionDate = i.fields.resolutiondate, issue.updateDate = i.fields.updated, issue.createDate = i.fields.created

            FOREACH (comm IN i.fields.comment.comments |
                MERGE (comment:Comment {id: comm.id}) ON CREATE SET comment.author = comm.author.key, comment.body = comm.body
                MERGE (comment)-[:ON]->(issue)
                MERGE (author:User {key: comm.author.key}) ON CREATE SET author.name = comm.author.name, author.displayName = comm.author.displayName, author.organization = comm.author.organization, author.ignore = comm.author.ignoreUser
                MERGE (author)-[:CREATED]->(comment)
            )
                """

    # Send Cypher query.
    graph.run(query, parameters={"json": json.loads(jsonData)})

# Set what organization the user is in according to data in orgData
def setOrgs(graph, orgData, fileName):
    path = "Data/Stored/" + fileName
    with open(path) as file:
        jsonData = json.loads(file.read())

    for item in jsonData["items"]:
        for comment in item["fields"]["comment"]["comments"]:
            byteKey = bytes(comment["author"]["key"], "UTF-8")
            if byteKey in orgData.keys():
                comment["author"]["organization"] = str(orgData[byteKey][0], "UTF-8")
                comment["author"]["ignoreUser"] = "false"
            else:
                comment["author"].pop("organization", None)
                comment["author"]["ignoreUser"] = "true"

    if os.path.exists(path):
        os.remove(path)
    with open(path, "w+") as storageFile:
        storageFile.write(json.dumps(jsonData))

    usersStrings = []
    for user in orgData:
        userStr = user.decode("utf-8")
        usersStrings.append(userStr)
        query = "MATCH (n:User) WHERE n.key = {userKey} SET n.organization = {org}, n.ignore = false"

        graph.run(query, {"userKey" : userStr, "org" : orgData[user][0].decode("utf-8")})

    query = "MATCH (n:User) WHERE NOT(n.key IN {userKeys}) SET n.organization = null, n.ignore = true"

    graph.run(query, {"userKeys" : usersStrings})


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
    query = """MATCH (n:User) WHERE NOT(n.ignore) RETURN n.key AS author, n.organization AS organization"""

    orgData = pd.DataFrame(graph.data(query))

    # Add column with total number of comments per issue to issueData
    issueData = pd.merge(issueData, totCommentsPerIssue, how="right", on="issueId")
    #
    # Add column with organizational affiliation
    issueData = pd.merge(issueData, orgData, how="inner", on="author")
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

def calcWeights(issueData):

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

    edges.to_json("Data/calculated.json", "records")

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

    centralityData.to_json("Data/calculated_metrics.json", "records")

    return centralityData

class HTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        graph = py2neo.Graph(neo4jLoc)

        parsedUrl = urlparse.urlparse(self.path)
        splitPath = parsedUrl.path.lstrip("/").split("/")
        parsedQuery = urlparse.parse_qs(parsedUrl.query)
        keys = parsedQuery.keys()

        # Send Sir Perceval on a quest to populate the Neo4j db
        if(len(splitPath) == 2 and splitPath[0] == 'quest'):
            fileName = scrapeDataToNeo(graph, urllib.parse.unquote(splitPath[1]), urllib.parse.unquote(parsedQuery['project'][0]), datetime.strptime(urllib.parse.unquote(parsedQuery['fromDate'][0]), '%m/%d/%Y'))
            self.send_response(200)
            self.send_header('Access-Control-Allow-Credentials', 'true')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(bytes(fileName, 'UTF-8'))
        else:
            if(splitPath[0] == "storedData"):
                response =  "{\"files\":[\"" + "\",\"".join(os.listdir("Data/Stored")) + "\"]}"
            elif(splitPath[0] == "issueTypes"):
                query = "MATCH (n:Issue) RETURN DISTINCT n.type AS type"
                issueTypes = graph.run(query)

                response = json.dumps(issueTypes.data())
            elif(splitPath[0] == "dates"):
                query = "MATCH (n:Issue) RETURN MIN(n.createDate) AS creationMin, MAX(n.createDate) AS creationMax, MIN(n.resolutionDate) AS resolutionMin, MAX(n.resolutionDate) AS resolutionMax"
                dates = graph.run(query)

                response = json.dumps(dates.data())
            elif(splitPath[0] == "users"):
                query = "MATCH (n:User) RETURN n.key AS username, n.displayName AS displayName, n.organization as organization, n.ignore as ignore"
                users = graph.run(query)

                response = json.dumps(users.data())
            else:
                if (len(keys) != 0 and 'issueTypes' in keys): # if there are no issueTypes then there is no response
                    issueTypes = parsedQuery['issueTypes'][0].split()
                    creationFromDate = parsedQuery['creationFromDate'][0] if 'creationFromDate' in keys else None
                    creationToDate = parsedQuery['creationToDate'][0] if 'creationToDate' in keys else None
                    resolutionFromDate = parsedQuery['resolutionFromDate'][0] if 'resolutionFromDate' in keys else None
                    resolutionToDate = parsedQuery['resolutionToDate'][0] if 'resolutionToDate' in keys else None
                    unresolved = parsedQuery['unResolved'][0] if 'unResolved' in keys else None

                    try:
                        res = readDB(graph, issueTypes, creationFromDate, creationToDate, resolutionFromDate, resolutionToDate, True if unresolved == "true" else False)
                        res = calcWeights(res)
                        res = genNetwork(res)
                    except (ZeroDivisionError, KeyError) as e:
                        self.send_header('Access-Control-Allow-Credentials', 'true')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.send_error(500, explain=str(type(e)).split("'")[1])
                        return
                    try:
                        file = open("Data/calculated" + splitPath[0] + ".json")
                    except IOError:
                        self.send_header('Access-Control-Allow-Credentials', 'true')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.send_error(404, self.path + " does not exist.")
                        return
                    response = file.read()
                else:
                    response = ' '

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Credentials', 'true')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(bytes(response, 'UTF-8'))
        return

    def do_POST(self):
        graph = py2neo.Graph(neo4jLoc)

        parsedUrl = urlparse.urlparse(self.path)
        splitPath = parsedUrl.path.lstrip("/").split("/")

        if(splitPath[0] == "usersToOrgs"):
            orgData = urlparse.parse_qs(self.rfile.read(int(self.headers.get('content-length'))))

            setOrgs(graph, orgData, urllib.parse.unquote(parsedUrl.query).replace("fileName=", "", 1))
        elif (splitPath[0] == "load"):
            fileNameParams = urlparse.parse_qs(self.rfile.read(int(self.headers.get('content-length'))))
            fileNameParams[b'url'][0] = urllib.parse.quote(fileNameParams[b'url'][0], safe="")
            fileName = "created=" + str(fileNameParams[b'created'][0], "UTF-8") + "&from=" + str(fileNameParams[b'from'][0], "UTF-8") + "&project=" + str(fileNameParams[b'project'][0], "UTF-8") + "&url=" + fileNameParams[b'url'][0]
            with open("Data/Stored/" + fileName) as file:
                populateNeoDb(graph, file.read())

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