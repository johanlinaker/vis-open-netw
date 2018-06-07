import requests
import json
from datetime import datetime

class GerritAPI:
    def __init__(self, url):
        self.url = url

    def fetch(self, from_date):
        response = requests.get(self.url+"changes/?q=after:"+from_date.strftime("%Y-%m-%d"))
        if(response.ok):
            data = json.loads(response.text.lstrip(")]}\'\n"))
            for change in data:
                change['comments'] = []
                comments = requests.get(self.url+"changes/"+change['id']+"/comments")
                comments = json.loads(comments.text.lstrip(")]}\'\n"))
                reviews = requests.get(self.url+"changes/"+change['id']+"/detail")
                reviews = json.loads(reviews.text.lstrip(")]}\'\n"))
                for file in comments:
                    for comm in comments[file]:
                        if comm['author']['_account_id'] != change['owner']['_account_id']:
                            comm['type'] = "line"
                            comm['file'] = file
                            if "Code-Review" in reviews['labels']:
                                rev = (review for review in reviews['labels']['Code-Review']['all'] if review['_account_id'] == comm['author']['_account_id'])
                                try:
                                    rev = next(rev)
                                    comm['vote'] = rev['value']
                                except StopIteration:
                                    comm['vote'] = 0
                            change['comments'].append(comm)
                comments = requests.get(self.url+"changes/"+change['id']+"/detail")
                comments = json.loads(comments.text.lstrip(")]}\'\n"))
                for comm in comments['messages']:
                    if comm['author']['_account_id'] != change['owner']['_account_id']:
                        comm['type'] = "general"
                        if "Code-Review" in reviews['labels']:
                            rev = (review for review in reviews['labels']['Code-Review']['all'] if review['_account_id'] == comm['author']['_account_id'])
                            try:
                                rev = next(rev)
                                comm['vote'] = rev['value']
                            except StopIteration:
                                comm['vote'] = 0
                        change['comments'].append(comm) 
                entry = {'data': change}
                yield entry

    def fetch_reviews(self, from_date):
        response = requests.get(self.url+"changes/?q=after:"+from_date.strftime("%Y-%m-%d"))
        if(response.ok):
            data = json.loads(response.text.lstrip(")]}\'\n"))
            for change in data:
                change['reviews'] = []
                reviews = requests.get(self.url+"changes/"+change['id']+"/detail")
                reviews = json.loads(reviews.text.lstrip(")]}\'\n"))
                if "Code-Review" in reviews['labels']:
                    for review in reviews['labels']['Code-Review']['all']:
                        if review['value'] is not 0:
                            change['reviews'].append(review)
                entry = {'data': change}
                yield entry
