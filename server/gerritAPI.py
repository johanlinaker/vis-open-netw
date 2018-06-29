import requests
import json
import time
import datetime

class GerritAPI:
    def __init__(self, url):
        self.url = url

    def fetch(self, from_date):
        before_date = (datetime.datetime.today() + datetime.timedelta(days=1)).isoformat().replace('T','+')
        while before_date[:10] > from_date.strftime("%Y-%m-%d"):
            print(before_date)
            print(self.url+"changes/?q=after:"+from_date.strftime("%Y-%m-%d")+"+AND+before:"+before_date[:10]+"+AND+status:merged")
            response = requests.get(self.url+"changes/?q=after:"+from_date.strftime("%Y-%m-%d")+"+AND+before:"+before_date[:10]+"+AND+status:merged")
            print(response.ok)
            if(response.ok):
                data = json.loads(response.text.lstrip(")]}\'\n"))
                if not data:
                    break
                before_date = (datetime.datetime.strptime(data[-1]['updated'][:10], '%Y-%m-%d') + datetime.timedelta(days=1)).isoformat().replace('T','+')
                for change in data:
                    change['comments'] = []
                    comments = requests.get(self.url+"changes/"+change['id']+"/comments")
                    if (not comments.ok):
                        before_date = change['updated'].replace(' ', '+')
                        break

                    try:
                        comments = json.loads(comments.text.lstrip(")]}\'\n"))
                    except:
                        print("Duplicate ids")
                        continue

                    reviews = requests.get(self.url+"changes/"+change['id']+"/detail")
                    if (not reviews.ok):
                        before_date = change['updated'].replace(' ', '+')
                        break

                    try:
                        reviews = json.loads(reviews.text.lstrip(")]}\'\n"))
                    except:
                        continue

                    change['owner'] = reviews['owner']
                    for file in comments:
                        for comm in comments[file]:
                            if "author" in comm:
                                comm['type'] = "line"
                                comm['file'] = file
                                if "labels" in  reviews and "Code-Review" in reviews['labels'] and "all" in reviews['labels']['Code-Review']:
                                    rev = (review for review in reviews['labels']['Code-Review']['all'] if review['_account_id'] == comm['author']['_account_id'])
                                    try:
                                        rev = next(rev)
                                        comm['vote'] = rev['value']
                                    except StopIteration:
                                        comm['vote'] = 0
                                change['comments'].append(comm)
                    comments = reviews
                    for comm in comments['messages']:
                        if "author" in comm:
                            comm['type'] = "general"
                            if "labels" in  reviews and "Code-Review" in reviews['labels'] and "all" in reviews['labels']['Code-Review']:
                                rev = (review for review in reviews['labels']['Code-Review']['all'] if review['_account_id'] == comm['author']['_account_id'])
                                try:
                                    rev = next(rev)
                                    comm['vote'] = rev['value']
                                except StopIteration:
                                    comm['vote'] = 0
                            change['comments'].append(comm) 
                    entry = {'data': change}
#                    time.sleep(30)
                    yield entry
            else:
                time.sleep(600)
