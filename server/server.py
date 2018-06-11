from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import threading
import argparse
import urllib.parse as urlparse

import pandas as pd
import networkx as nx
from perceval.backends.core import jira as percJira
from perceval.backends.core import github as percGithub
from perceval.backends.core import gerrit as percGerrit
from perceval.backends.core import mbox as percMbox
import gerritAPI as gerrit

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

def scrapeDataToNeo(graph, url=None, project=None, owner=None, repository=None, api_token=None, hostname=None, uri=None, dir=None, fromDateTime=None):
    perceval = None
    type = None
    if url is not None and project is not None:
        perceval = percJira.Jira(url, project=project)
        type = "jira"
    elif owner is not None and repository is not None:
        type= "github"
        if api_token is not None:
            perceval = percGithub.GitHub(owner=owner, repository=repository, api_token=api_token)
        else:
            perceval = percGithub.GitHub(owner=owner, repository=repository)
    elif hostname is not None:
        type = "gerrit"
        perceval = gerrit.GerritAPI(hostname)
    elif dir is not None: 
        type = "email"
        perceval = percMbox.MBox(uri, dir)
    issues = perceval.fetch(from_date=fromDateTime)

    buf = '{\n\"items\": ['
    first = True
    for issue in issues:
        if not first:
            buf += ','
        first = False
        buf += json.dumps(issue['data'])
        print(issue['data']['From'])
    buf += ']\n}'
    buf = buf.replace("<", "(")
    buf = buf.replace(">", ")")

    # Save buffered data for later usage
    filename = "created=" + datetime.utcnow().strftime("%d-%m-%Y") + "&from=" + fromDateTime.strftime(
            "%d-%m-%Y")
    if type is "jira":
        filename = filename + "&project=" + project + "&url=" + urllib.parse.quote(url, safe="")
    elif type is "github": 
        filename = filename + "&owner=" + owner + "&repository=" + repository
    elif type is "gerrit":
        filename = filename + "&hostname=" + urllib.parse.quote(hostname, safe="")
    elif type is "email":
        filename = filename + "&uri=" + urllib.parse.quote(uri, safe="") + "&directory=" + dir

    path = "Data/Stored/" + filename
    if os.path.exists(path):
        os.remove(path)
    with open(path, "w+") as storageFile:
        storageFile.write(buf)

    populateNeoDb(graph, buf, type)

    return filename

def populateNeoDb(graph, jsonData, type):
    cleanDataDir()

    graph.delete_all()
    graph.run("CREATE CONSTRAINT ON (u:User) ASSERT u.key IS UNIQUE;")
    jsonData = json.loads(jsonData)

    # Build query - This is JIRA-backend-specific
    if type is "jira":
        query = """
                WITH {json} as data
                UNWIND data.items as i
                MERGE (issue:Issue {id:i.id}) ON CREATE
                  SET issue.key = i.key, issue.type = i.fields.issuetype.name, issue.resolutionDate = i.fields.resolutiondate, issue.updateDate = i.fields.updated, issue.createDate = i.fields.created, issue.priority = i.fields.priority.name, issue.src = "jira"

                FOREACH (comm IN i.fields.comment.comments |
                    MERGE (comment:Comment {id: comm.id}) ON CREATE SET comment.author = comm.author.key, comment.body = comm.body, comment.src = "jira"
                    MERGE (comment)-[:ON]->(issue)
                    MERGE (author:User {key: comm.author.key}) ON CREATE SET author.name = comm.author.name, author.displayName = comm.author.displayName, author.emailAddress = comm.author.emailAddress, author.organization = comm.author.organization, author.ignore = CASE comm.author.ignoreUser WHEN "true" THEN true ELSE false END
                    MERGE (author)-[:CREATED]->(comment)
                )
                """
    elif type is "github":
        query = """
                WITH {json} as data
                UNWIND data.items as i
                MERGE (issue:Issue {id:i.number}) ON CREATE
                  SET issue.key = i.title, issue.type = i.state, issue.resolutionDate = i.closed_at, issue.updateDate = i.updated_at, issue.createDate = i.created_at, issue.priority = "", issue.src = "github"
		MERGE (comment:Comment {id: i.id}) ON CREATE SET comment.author = i.user_data.login, comment.body = i.body, comment.src = "github"
                MERGE (comment)-[:ON]->(issue)
                MERGE (author:User {key: i.user_data.login}) ON CREATE SET author.name = i.user_data.login, author.displayName = i.user_data.name, author.emailAddress = i.user_data.email, author.organization = i.user_data.company, author.ignore = CASE i.user_data.ignoreUser WHEN "true" THEN true ELSE false END
                MERGE (author)-[:CREATED]->(comment)

                FOREACH (comm IN i.comments_data |
                    MERGE (comment:Comment {id: comm.id}) ON CREATE SET comment.author = comm.user_data.login, comment.body = comm.body, comment.src = "github"
                    MERGE (comment)-[:ON]->(issue)
                    MERGE (author:User {key: comm.user_data.login}) ON CREATE SET author.name = comm.user_data.login, author.displayName = comm.user_data.name, author.emailAddress = comm.user_data.email, author.organization = comm.user_data.company, author.ignore = CASE comm.user_data.ignoreUser WHEN "true" THEN true ELSE false END
                    MERGE (author)-[:CREATED]->(comment)
                )
                """
    elif type is "gerrit":
        for item in jsonData['items']:
            for comm in item['comments']:
                if "username" not in comm['author']:
                    comm['author']['username'] = comm['author']['email'].split("@")[0]
        query = """
                WITH {json} as data
                UNWIND data.items as i
                MERGE (issue:Issue {id:i.id}) ON CREATE
                  SET issue.key = i.subject, issue.type = i.status, issue.resolutionDate = i.resolutiondate, issue.updateDate = i.updated, issue.createDate = i.created, issue.priority = i.priority, issue.src = "gerrit"
                FOREACH (comm IN i.comments |
                    MERGE (comment:Comment {id: comm.id}) ON CREATE SET comment.author = comm.author.username, comment.body = comm.message, comment.vote = comm.vote, comment.src = "gerrit"
                    MERGE (comment)-[:ON]->(issue)
                    MERGE (author:User {key: comm.author.username}) ON CREATE SET author.name = comm.author.username, author.displayName = comm.author.name, author.emailAddress = comm.author.email, author.organization = comm.author.organization, author.ignore = CASE comm.author.ignoreUser WHEN "true" THEN true ELSE false END
                    MERGE (author)-[:CREATED]->(comment)
                )
                """
    elif type is "email":
        for item in jsonData['items']:
            item['id'] = item['Message-ID']
            if item['Subject'].startswith("Re: "):
                item['Subject'] = item['Subject'][4:]
#            if 'Name' not in item:
#                item['Name'] = item['From'].split("<",1)[0]
#            if 'Email' not in item:
#                item['Email'] = item['From'].split("<",1)[1][:-1]

        query = """
                WITH {json} as data
                UNWIND data.items as i
                MERGE (issue:Issue {id:i.Subject}) ON CREATE
                  SET issue.key = i.Subject, issue.type = "Message", issue.resolutionDate = "2018-01-01T00:00:00.000+0000", issue.updateDate = "2018-01-01T00:00:00.000+0000", issue.createDate = "2018-01-01T00:00:00.000+0000", issue.priority = i.priority, issue.src = "email"
                MERGE (comment:Comment {id: i.id}) ON CREATE SET comment.author = i.From, comment.body = i.body.plain, comment.src = "email"
                MERGE (comment)-[:ON]->(issue)
                MERGE (author:User {key: i.From}) ON CREATE SET author.name = i.From, author.displayName= i.From, author.emailAddress = i.From, author.organization = i.organization, author.ignore = CASE i.ignoreUser WHEN "true" THEN true ELSE false END
                MERGE (author)-[:CREATED]->(comment)
                """

    # Send Cypher query.
    graph.run(query, parameters={"json": jsonData})

    # Add defaults values for null fields
    query = """MATCH (n:User) RETURN n.key AS key, n.emailAddress AS emailAddress, n.organization AS organization, n.displayName AS displayName"""

    userData = pd.DataFrame(graph.data(query))
    if len(userData.index) > 0:
        userData['emailAddress'] = userData['emailAddress'].replace({' at ': '@', ' dot ': '.'}, regex=True)
        defaultOrg = userData['emailAddress'].str.extract(r'\@(.*)\.')

        for user in userData.itertuples():
            index, displayName, emailAddress, key, organization = user
            if emailAddress is None:
                emailAddress = "No Email Given"
                defaultOrg[index] = "No Org Given"
            if organization is None:
                organization = defaultOrg[index]
            if displayName is None:
                displayName = key
            displayName = displayName.replace("'", "")
            query = "MATCH (n:User) WHERE n.key = '" + key + "' SET n.emailAddress = '" + emailAddress + "', n.organization = '" + organization + "', n.displayName = '" + displayName + "'"
            graph.run(query)

# Set what organization the user is in according to data in orgData
def setOrgs(graph, orgData, fileName):
    path = "Data/Stored/" + fileName
    with open(path) as file:
       	jsonData = json.loads(file.read())

    if "url" in fileName and "project" in fileName:
        for item in jsonData["items"]:
            for comment in item["fields"]["comment"]["comments"]:
                key = comment["author"]["key"]
                if key in orgData.keys():
                    comment["author"]["organization"] = orgData[key][0]
                    comment["author"]["ignoreUser"] = "false"
                else:
                    comment["author"].pop("organization", None)
                    comment["author"]["ignoreUser"] = "true"
    elif "owner" in fileName and "repository" in fileName:
        for item in jsonData["items"]:
            key = item["user_data"]["login"]
            if key in orgData.keys():
                item["user_data"]["company"] = orgData[key][0]
                item["user_data"]["ignoreUser"] = "false"
            else:
                item["user_data"].pop("company", None)
                item["user_data"]["ignoreUser"] = "true"
            for comment in item["comments_data"]:
                key = comment["user_data"]["login"]
                if key in orgData.keys():
                    comment["user_data"]["company"] = orgData[key][0]
                    comment["user_data"]["ignoreUser"] = "false"
                else:
                    comment["user_data"].pop("company", None)
                    comment["user_data"]["ignoreUser"] = "true"
    elif "hostname" in fileName:
        for item in jsonData["items"]:
            for comment in item["comments"]:
                key = comment["author"]['email'].split("@")[0]
                if "username" in comment["author"]:
                    key = comment["author"]["username"]
                if key in orgData.keys():
                    comment["author"]["organization"] = orgData[key][0]
                    comment["author"]["ignoreUser"] = "false"
                else:
                    comment["author"].pop("organization", None)
                    comment["author"]["ignoreUser"] = "true"
    elif "uri" in fileName:
        for item in jsonData["items"]:
            key = item["From"]
            if key in orgData.keys():
                item["organization"] = orgData[key][0]
                item["ignoreUser"] = "false"
            else:
                item.pop("organization", None)
                item["ignoreUser"] = "true"

    if os.path.exists(path):
        os.remove(path)
    with open(path, "w+") as storageFile:
        storageFile.write(json.dumps(jsonData))

    usersStrings = []
    for user in orgData:
        userStr = user
        usersStrings.append(userStr)
        query = "MATCH (n:User) WHERE n.key = {userKey} SET n.organization = {org}, n.ignore = false"
        graph.run(query, {"userKey" : userStr, "org" : orgData[user][0]})

    query = "MATCH (n:User) WHERE NOT(n.key IN {userKeys}) SET n.organization = null, n.ignore = true"

    graph.run(query, {"userKeys" : usersStrings})


def readDB(graph, issueTypes, creationFromDate = None, creationToDate = None, resolutionFromDate = None, resolutionToDate = None, unresolved = True, priorities = [], voteThreshold = None):
    params = {}
    # Nbr of comments per user and issue
    # author | issueId | anchor | nbrOfComments
    query = """MATCH (n:Comment)-[r:ON]->(i:Issue)"""

    query = query + """ WHERE i.type IN {issueTypes}"""
    params['issueTypes'] = issueTypes

    if(len(priorities) > 0):
        query = query + """ AND i.priority IN {priorities} """
        params['priorities'] = priorities

    if(voteThreshold is not None):
        if (voteThreshold > 0):
            query = query + """ AND n.vote > 0 """
        elif (voteThreshold < 0):
            query = query + """ AND n.vote < 0 """

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

    # Remove rows with missing values
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
    try:
        eigenvector = nx.eigenvector_centrality(netw)
    except:
        eigenvector = nx.eigenvector_centrality_numpy(netw)

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

def getEdgeData(graph, issueTypes, org1, org2, creationFromDate = None, creationToDate = None, resolutionFromDate = None, resolutionToDate = None, unresolved = True, priorities = [], voteThreshold = None):
    params = {}
    # Nbr of comments per user and issue
    # author | issueId | anchor | nbrOfComments
    query = """MATCH (n:User)-[r1:CREATED]->(c:Comment)-[r2:ON]->(i:Issue) """

    query = query + """ WHERE i.type IN {issueTypes}"""
    params['issueTypes'] = issueTypes

    if(voteThreshold is not None):
        if (voteThreshold > 0):
            query = query + """ AND c.vote > 0 """
        elif (voteThreshold < 0):
            query = query + """ AND c.vote < 0 """

    query = query + """ AND n.organization = {org1} """
    params['org1'] = org1

    if(len(priorities) > 0):
        query = query + """ AND i.priority IN {priorities} """
        params['priorities'] = priorities

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

    query = query + """ RETURN n.key as author, i.key as issueId, count(r1) as numOfComments"""
    issueData = pd.DataFrame(graph.data(query, parameters=params))

    query = """MATCH (n:User)-[r1:CREATED]->(c:Comment)-[r2:ON]->(i:Issue) WHERE n.organization = {org2} RETURN DISTINCT i.key as issueId"""
    collaborators = pd.DataFrame(graph.data(query, parameters={'org2': org2}))

    query = """MATCH (c:Comment)-[r:ON]->(i:Issue) RETURN i.key as issueId, count(r) as issueComments"""
    commentCounts = pd.DataFrame(graph.data(query, parameters={'org2': org2}))

    issueData = pd.merge(issueData, collaborators, how="inner", on="issueId")
    issueData = pd.merge(issueData, commentCounts, how="inner", on="issueId")

    issueData = issueData.groupby(['author', 'issueId', 'issueComments']).sum().reset_index()

    return issueData.to_json("Data/calculated_edge.json", "records")

class HTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        graph = py2neo.Graph(neo4jLoc)

        parsedUrl = urlparse.urlparse(self.path)
        splitPath = parsedUrl.path.lstrip("/").split("/")
        parsedQuery = urlparse.parse_qs(parsedUrl.query)
        keys = parsedQuery.keys()

        # Send Sir Perceval on a quest to populate the Neo4j db
        if(len(splitPath) == 2 and splitPath[0] == 'quest'):
            fileName = None
            if ('project' in keys):
                fileName = scrapeDataToNeo(graph, url=urllib.parse.unquote(splitPath[1]), project=urllib.parse.unquote(parsedQuery['project'][0]), fromDateTime=datetime.strptime(urllib.parse.unquote(parsedQuery['fromDate'][0]), '%m/%d/%Y'))
            elif ('owner' in keys and 'repository' in keys and 'api_token' in keys):
                fileName = scrapeDataToNeo(graph, owner=urllib.parse.unquote(parsedQuery['owner'][0]), repository=urllib.parse.unquote(parsedQuery['repository'][0]), api_token=urllib.parse.unquote(parsedQuery['api_token'][0]), fromDateTime=datetime.strptime(urllib.parse.unquote(parsedQuery['fromDate'][0]), '%m/%d/%Y'))
            elif 'hostname' in keys:
                fileName = scrapeDataToNeo(graph, hostname=urllib.parse.unquote(parsedQuery['hostname'][0]), fromDateTime=datetime.strptime(urllib.parse.unquote(parsedQuery['fromDate'][0]), '%m/%d/%Y'))
            elif 'uri' in keys and 'directory' in keys:
                fileName = scrapeDataToNeo(graph, uri=urllib.parse.unquote(parsedQuery['uri'][0]), dir=urllib.parse.unquote(parsedQuery['directory'][0]), fromDateTime=datetime.strptime(urllib.parse.unquote(parsedQuery['fromDate'][0]), '%m/%d/%Y'))
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
            elif(splitPath[0] == "priorities"):
                query = "MATCH (n:Issue) RETURN DISTINCT n.priority AS priority"
                priorities = graph.run(query)

                response = json.dumps(priorities.data())
            elif(splitPath[0] == "users"):
                query = "MATCH (n:User) RETURN n.key AS username, n.displayName AS displayName, n.emailAddress AS emailAddress, n.organization AS organization, n.ignore AS ignore"
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
                    priorities = parsedQuery['priorities'][0].split() if 'priorities' in keys else []
                    sentiment = int(parsedQuery['sentiment'][0]) if 'sentiment' in keys else None
                    org1 = parsedQuery['org1'][0] if 'org1' in keys else None
                    org2 = parsedQuery['org2'][0] if 'org2' in keys else None

                    try:
                        res = readDB(graph, issueTypes, creationFromDate, creationToDate, resolutionFromDate, resolutionToDate, True if unresolved == "true" else False, priorities, sentiment)
                        res = calcWeights(res)
                        res = genNetwork(res)
                        if (org1 is not None and org2 is not None):
                            res2 = getEdgeData(graph, issueTypes, org1, org2, creationFromDate, creationToDate, resolutionFromDate, resolutionToDate, True if unresolved == "true" else False, priorities, sentiment)
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
            orgData = urlparse.parse_qs(self.rfile.read(int(self.headers.get('content-length'))).decode('ascii'))
            setOrgs(graph, orgData, urllib.parse.unquote(parsedUrl.query).replace("fileName=", "", 1))
        elif(splitPath[0] == "load"):
            filename = self.getFilePathFromPostData()
            with open(filename) as file:
                if "url" in filename and "project" in filename:
                    populateNeoDb(graph, file.read(), "jira")
                elif "owner" in filename and "repository" in filename:
                    populateNeoDb(graph, file.read(), "github")
                elif "hostname" in filename:
                    populateNeoDb(graph, file.read(), "gerrit")
                elif "uri" in filename:
                    populateNeoDb(graph, file.read(), "email")
        elif(splitPath[0] == "deleteData"):
            os.remove(self.getFilePathFromPostData())

    def getFilePathFromPostData(self):
        fileNameParams = urlparse.parse_qs(self.rfile.read(int(self.headers.get('content-length'))))
        fileName = "created=" + str(fileNameParams[b'created'][0], "UTF-8") + "&from=" + str(
            fileNameParams[b'from'][0], "UTF-8")
        if b'url' in fileNameParams and b'project' in fileNameParams:
            fileNameParams[b'url'][0] = urllib.parse.quote(fileNameParams[b'url'][0], safe="")
            fileName = fileName + "&project=" + str(fileNameParams[b'project'][0], "UTF-8") + "&url=" + fileNameParams[b'url'][0]
        elif b'owner' in fileNameParams and b'repository' in fileNameParams:
            fileName = fileName + "&owner=" + str(fileNameParams[b'owner'][0], "UTF-8") + "&repository=" + str(fileNameParams[b'repository'][0], "UTF-8")
        elif b'hostname' in fileNameParams:
            fileNameParams[b'hostname'][0] = urllib.parse.quote(fileNameParams[b'hostname'][0], safe="")
            fileName = fileName + "&hostname=" + fileNameParams[b'hostname'][0]
        elif b'uri' in fileNameParams:
            fileNameParams[b'uri'][0] = urllib.parse.quote(fileNameParams[b'uri'][0], safe="")
            fileName = fileName + "&uri=" + fileNameParams[b'uri'][0] + "&directory=" + str(fileNameParams[b'directory'][0], "UTF-8")
        return "Data/Stored/" + fileName

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
