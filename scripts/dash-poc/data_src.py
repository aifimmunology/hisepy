from dash import html, dcc, Dash
from dash.dependencies import Input, Output
import plotly.express as px
import plotly.graph_objects as go
import hisepy
import uuid

import pandas as pd

df = pd.read_csv('https://raw.githubusercontent.com/plotly/datasets/master/gapminderDataFiveYear.csv')

app = Dash(__name__)

app.layout = html.Div([
    dcc.Graph(id='hise-graph'),
    html.Div([
        "TraceId: ",
        dcc.Input(id='trace-id', value='', type='text', size="40")
    ]),
])

uuid_none = uuid.UUID(int = 0)

@app.callback(
    Output('hise-graph', 'figure'),
    Input('trace-id', 'value'))
def update_figure(trace_id):
    if trace_id is None or len(trace_id) != len(format(uuid_none)):
        return empty_plot("Potatoes")

    try:
        tr = hisepy.get_trace(trace_id)
        data = hisepy.load_visualization_data(tr["steps"]["dataReference"])
        for d in data:
            figure(d)
    except Exception as e:
        return empty_plot(format(e))
    print("STOATS")
    return figure()
        
if __name__ == '__main__':
    app.run_server(debug=True)
    
def empty_plot(msg):
    return go.Figure({
        "layout": {
            "xaxis": {
                "visible": False
            },
            "yaxis": {
                "visible": False
            },
            "annotations": [
                {
                    "text": msg,
                    "xref": "paper",
                    "yref": "paper",
                    "showarrow": False,
                    "font": {
                        "size": 28
                    }
                }
            ]
        }
    })
fig = hisepy.load_visualization_layout("67bfe11c-c16d-47ce-bea5-0c7516e92bfe")

def figure(data = None):
    print("Called figure")
    if data is not None:
        fig.add_trace(d)
    return fig

