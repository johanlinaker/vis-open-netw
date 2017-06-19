# vis-open-netw
Tool-support for Analysis and Visualization of Companies Involved in Open Source Software Communities

Currently this application only works for JIRA.

# Requirements
    Python >= 3.4
    python3-dateutil >= 2.6
    python3-requests >= 2.7
    python3-bs4 (beautifulsoup4) >= 4.3
    python3-feedparser >= 5.1.3
    grimoirelab-toolkit >= 0.1.0
    urllib3 >= 1.9
    pandas >= 0.20.1
    networkx >= 1.11
    py2neo >= 3.1.2

# Set-up

1. Clone this repo
2. Install Neo4j - https://neo4j.com/download/community-edition/
    - Go to http://localhost:7474/browser/ and change the neo4j user password to "lund101"
3. Run server.py
4. Run index.html on port 8383
5. Go to http://localhost:8383/visualizationProject/index.html

# JIRA Specifics

There are some JIRA-specific elements, specifically the query used to populate the neo4j graph from the json data that comes from the included version of Perceval, and the included version of Perceval has some edits to allow it to grab comments from JIRA (see the Perceval section below).

# Perceval

This repo includes a copy of Perceval (https://github.com/grimoirelab/perceval) that contains a change to the JIRA backend. This change allows Perceval to grab the comments for each issue.

In the future it would be desirable to make a switch for the Perceval JIRA backend for grabbing JIRA issue comments and to create a PR in the Perceval git repo so that the offical, supported, version of perceval can be used in this application instead of the copy included.
