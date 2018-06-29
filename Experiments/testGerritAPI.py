import requests
import json

url = "https://gerrit.opnfv.org/gerrit/"
response = requests.get(url+"changes/?q=status:open+after:2018-05-22")
print(response.status_code)

if(response.ok):
    response = response.text.lstrip(")]}\'\n")
    data = json.loads(response)
    for item in data:
        print(item['subject'])
        changeComments = requests.get(url+"changes/"+item['id']+"/comments")
        changeComments = json.loads(changeComments.text.lstrip(")]}\'\n"))
        for file in changeComments:
            for comm in changeComments[file]:
                print(comm)
