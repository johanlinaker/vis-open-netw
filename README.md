# StakeViz
StakeViz is a tool for analysis and visualization of stakeholders involved in Open Source Software (OSS) communities. It scrapes communication and contribution data from community repositories and creates networks based on how stakeholders (individuals and/or organizations) has interacted (e.g., commented on the same issue, or contributed a commit to the same file). The tool then allows you to visually analyze who collaborates with whom, and leverage centrlality metrics to point out those with the higest influence, and that contributed the most. 

Currently this application is limited to only scrape data from JIRA issue trackers enabled by custimization to the [Perceval](https://github.com/grimoirelab/perceval) project. Support for further types of repositories will be added in the future.

Note that there should only be one connection to the server running via ./server/server.py at a time for proper operation.

# Requirements
    Python >= 3.4
    python3-setuptools >= 20.7.0

# Set-up

1. Clone this repo
2. Clone and install our [Perceval fork](https://github.com/johanlinaker/perceval)
    - Note that you may need to uninstall Perceval if you have a copy already
3. Install Requirements (above), e.g., using apt-get or pip3
4. Run
```
$ pip3 install -r requirements.txt
```
5. Download and boot up [neo4j](https://neo4j.com/download/community-edition/)
    - Go to http://localhost:7474/browser/ and change the default user password from "neo4j" to "lund101"
6. Run "python3 ./server/server.py 8080 localhost"
7. Run ./visualizationProject/public_html/index.html on port 8383 (for example, by running "python3 -m http.server 8383" while in the top-level directory for this project)
8. Go to http://localhost:8383/visualizationProject/public_html/index.html

# JIRA Specifics

There are some JIRA-specific elements, specifically the query used to populate the neo4j graph from the json data that comes from the forked version of Perceval, and the forked version of Perceval has some edits to allow it to grab comments from JIRA (see the Perceval section below).

# Perceval

This project uses a fork of [Perceval](https://github.com/johanlinaker/perceval) that contains a change to the JIRA and GitHub backends. This change allows Perceval to grab the comments for each issue.

In the future it would be desirable to make a switch for the Perceval JIRA backend for grabbing JIRA issue comments and to create a PR in the original Perceval git repo so that the offical, supported, version of perceval can be used in this application instead of our fork.

# Overview

- Neo4j is used as a database to store the data scraped.
- The python server.py script services requests for the data in the database, so the main purpose of the script is to translate HTTP requests to Neo4j queries and to take the Neo4j responses and to translate the data into formats the front-end can consume
- The python server.py script is also responsible for saving the data locally so that redundant scrapes do not have to be made.
- The front-end is, in majority, in javascript, utilizing jQuery for organizing and manipulating the HTML, and vis.js for creating the front-end graph. Requests are sent to the python server using ajax queries.

- The connections between organizations are visualized in the graph on the left of the page with specific centrality metrics for each organization in a table on the right. Selecting a specific node in the graph will hide all nodes not connected to it, and double clicking on it will put it in a hierarchal structure. Selecting an edge will bring up a table listing the interaction between the two nodes. The view can be reset by clicking on empty space in the graph.

- To add support for other Perceval back-ends changes should only need to be made to the python script (in fact, only the import script should need to change, along with Perceval call changes)
    - Note: The Perceval back-end itself may need to be changed, but this will need to be determined on a case-by-case basis
    - Currently, StakeViz supports scraping from JIRA, GitHub, and Mailing Lists via Perceval as well as Gerrit via a custom python script that scrapes the Gerrit API. For Mailing Lists, a local MBox must be present to scrape
    
- Data from multiple sources can be pulled into the database simultaneously allowing for the sources to be synthesized together for analysis. The user chooses whether to reset the database each they load in from a new source, and the raw data for each source is stored in a separate local file.
    - In cases that a single user is represented differently in multiple sources, they can be merged while setting their organization.

- Once loaded into StakeViz, the data can be filtered based on the Issue Type, Priority, Creation Date, and Resolution Date. Additionally, Gerrit reviews can be further filtered by sentiment of review (either the review score left or value determined by performing sentiment analysis on the message)
    - Note: Priority may not be present as filter for all data types
    - Sentiment analysis done using SentiCR (https://github.com/senticr/SentiCR)
