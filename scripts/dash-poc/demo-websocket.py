import json
import uuid

import time

import hisepy

seen = {}
completed = False
opened = False
data = []


def get_query(query_id):
    if query_id is None or len(query_id) != len(format(uuid_none)):
        return fig

    if query_id in seen:
        print("Already saw %s" % (query_id))
        return fig

    seen[query_id] = True
    try:
        add_files(hisepy.get_files_for_query(query_id))
    except Exception as e:
        print("Nope: %s" % (format(e)))
        completed = True
    return fig


def add_files(files):
    ws.send(
        json.dumps({
            "command": "stream",
            "format": [{
                "x": ["population"],
                "y": ["count"]
            }],
            "filesPerMessage": 1,
            "fileIds": files
        }))
    print("Added %d files" % (len(files)))


def ws_open(ws):
    print("Websocket opened")
    opened = True


def ws_message(ws, message):
    obj = None
    print("Got message")
    try:
        obj = json.loads(message)
        for d in obj["data"]:
            fig.add_trace(d)
        if obj["remainingFiles"] == 0:
            print("Read all files, saving visualization")
            tr = save_visualization(fig)
            print("Trace is %s" % (tr))
            completed = True
        else:
            print("%d remaining files" % (obj["remainingFiles"]))
    except Exception as e:
        print("Message failure: %s" % (format(e)))
        completed = True


def empty_plot(msg):
    return go.Figure({
        "layout": {
            "xaxis": {
                "visible": False
            },
            "yaxis": {
                "visible": False
            },
            "annotations": [{
                "text": msg,
                "xref": "paper",
                "yref": "paper",
                "showarrow": False,
                "font": {
                    "size": 28
                }
            }]
        }
    })


uuid_none = uuid.UUID(int=0)
fig = hisepy.load_visualization_layout("ff974deb-0b13-40f8-8e61-47fe82652f5d")
rando_query = "39a8304b-a334-40a5-8608-e7f5077b595e"
ws = hisepy.hise_websocket(ws_open, ws_message)
ws.run_forever(origin="http://localhost:3000")
print("Here")
while not opened:
    time.sleep(1)
print("Getting query")
get_query(rando_query)
while not completed:
    time.sleep(1)

ws.close()
print("Done")
exit(0)
