# vis-open-netw
StakeViz is a tool for analysis and visualization of stakeholders involved in Open Source Software (OSS) communities. It scrapes communication and contribution data from community repositories and creates networks based on how stakeholders (individuals and/or organizations) has interacted (e.g., commented on the same issue, or contributed a commit to the same file). The tool then allows you to visually analyze who collaborates with whom, and leverage centrlality metrics to point out those with the higest influence, and that contributed the most. 

Currently this application is limited to only scrape data from JIRA issue trackers enabled by custimization to the [Perceval](https://github.com/grimoirelab/perceval) project. Support for further types of repositories will be added in the future.

Note that there should only be one connection to the server running via ./server/server.py at a time for proper operation.

# Requirements
    Python >= 3.4
    python3-dateutil >= 2.6
    python3-requests >= 2.7
    python3-bs4 (beautifulsoup4) >= 4.3
    python3-feedparser >= 5.1.3
    python3-setuptools >= 20.7.0
    grimoirelab-toolkit >= 0.1.0
    python3-urllib3 >= 1.9
    python3-pandas >= 0.20.1
    python3-networkx >= 1.11
    py2neo >= 3.1.2

# Set-up

1. Clone this repo
2. Install Requirements (above), e.g., using apt-get or pip3
    - The [grimoirelab-toolkit](https://github.com/grimoirelab/grimoirelab-toolkit) needs to be cloned and installed manually.
    - Note that you may also need to uninstall Perceval if you have a copy already
3. Go to ./visualizationProject/perceval and run "python3 setup.py install"
4. Download and boot up [neo4j](https://neo4j.com/download/community-edition/)
    - Go to http://localhost:7474/browser/ and change the default user password from "neo4j" to "lund101"
5. Run "python3 ./server/server.py 8080 localhost"
6. Run ./visualizationProject/public_html/index.html on port 8383 (for example, by running "python3 -m http.server 8383" while in the top-level directory for this project)
7. Go to http://localhost:8383/visualizationProject/public_html/index.html

# JIRA Specifics

There are some JIRA-specific elements, specifically the query used to populate the neo4j graph from the json data that comes from the included version of Perceval, and the included version of Perceval has some edits to allow it to grab comments from JIRA (see the Perceval section below).

# Perceval

This repo includes a copy of [Perceval](https://github.com/grimoirelab/perceval) that contains a change to the JIRA backend. This change allows Perceval to grab the comments for each issue.

In the future it would be desirable to make a switch for the Perceval JIRA backend for grabbing JIRA issue comments and to create a PR in the Perceval git repo so that the offical, supported, version of perceval can be used in this application instead of the copy included.

# Overview

- Neo4j is used as a database to store the data scraped by the included version of Perceval.
- The python server.py script services requests for the data in the database, so the main purpose of the script is to translate HTTP requests to Neo4j queries and to take the Neo4j responses and to translate the data into formats the front-end can consume
- The front-end is, in majority, in javascript, utilizing jQuery for organizing and manipulating the HTML, and vis.js for creating the front-end graph. Requests are sent to the python server using ajax queries.

- To add support for other Perceval back-ends changes should only need to be made to the python script (in fact, only the import script should need to change, along with Perceval call changes)
    - Note: The Perceval back-end itself may need to be changed, but this will need to be determined on a case-by-case basis
