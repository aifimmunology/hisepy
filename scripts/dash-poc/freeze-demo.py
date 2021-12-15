import dash
import plotly.express as px
import pandas as pd
import hisepy
import flask
import pathlib

app = dash.Dash(__name__)

# assume you have a "long-form" data frame
# see https://plotly.com/python/px-arguments/ for more options
df = pd.DataFrame({
    "Fruit": ["Apples", "Oranges", "Bananas", "Apples", "Oranges", "Bananas"],
    "Amount": [4, 1, 2, 2, 4, 5],
    "City": ["SF", "SF", "SF", "Montreal", "Montreal", "Montreal"]
})

fig = px.bar(df, x="Fruit", y="Amount", color="City", barmode="group")
# new_trace = hisepy.save_visualization(fig,
#                                       title = "Dash Demo Thing Dealiebob",
#                                       study_space_id = "07385734-b01b-4932-9a77-4706ced71d63")
# print(new_trace)
#trace_id = "e225781d-7eba-4351-84f7-fdc0840ddb92"
trace_id = "ff974deb-0b13-40f8-8e61-47fe82652f5d"
#trace_id = "25d7f47a-183f-4894-83a7-28cd472b9dd0"
#trace_id = "6b2a0e72-b4a3-4da3-9336-07b6b129073b"
#trace_id = "67bfe11c-c16d-47ce-bea5-0c7516e92bfe"

app.layout = dash.html.Div(children=[
    dash.html.H1(children='Hello Dash'),

    dash.html.Div(children='''
        Dash: A web application framework for your data.
    '''),

    dash.dcc.Graph(
        id='example-graph',
        figure=fig
    ),

    dash.html.Div(children='''
        HISE: All yr base r belong to us
    '''),
    
    dash.dcc.Graph(
        id='hise-graph',
        figure=hisepy.load_visualization(trace_id)),

])

if __name__ == '__main__':
    spaces = hisepy.get_study_spaces()
    trace = hisepy.get_trace(trace_id)
    hisepy.freeze_dash_app(app,
                           study_space_id = spaces[0]["id"],
                           title = "Freezer Demo",
                           input_file_ids = [trace["steps"]["dataReference"]])
    app.run_server(debug=True)

