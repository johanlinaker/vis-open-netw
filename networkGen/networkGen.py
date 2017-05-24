import pandas as pd
import networkx as nx
# import matplotlib.pyplot as plt
import pymysql

import csv
import json

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

    dbOutputFileName = "01_dbOutput"
    dbOutputFileCSVName = dbOutputFileName + ".csv"
    issueData.to_csv(dbOutputFileCSVName)

    with open(dbOutputFileCSVName) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    with open(dbOutputFileName + ".json", 'w') as f:
        json.dump(rows, f)

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
                                "collabOrganization": "to"}, inplace=True)

    issueOutputFileName = "02_weightOutput"
    issueOutputFileCSVName = issueOutputFileName + ".csv"
    edges.to_csv(issueOutputFileCSVName)

    with open(issueOutputFileCSVName) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    with open(issueOutputFileName + ".json", 'w') as f:
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

    with open(centralityOutputFileName + ".json", 'w') as f:
        json.dump(rows, f)

    return centralityData

def main():
    res = readDB("kylec")
    res = calcWeights(res)
    res = genNetwork(res)

if  __name__ =='__main__':main()