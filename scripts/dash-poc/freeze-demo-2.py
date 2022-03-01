import plotly.graph_objects as go
import plotly.express as px
import hisepy as hp
import dash

df_scatter = px.data.iris()
fig_scatter = px.scatter(df_scatter, x="sepal_width", y="sepal_length", color="species", symbol="species")

df_fig = px.data.tips()
fig_box = px.box(df_fig, x="time", y="total_bill", points="all")

ss = hp.get_study_spaces()
files_that_definitely_contributed_to_this_app = ["0fb06e51-74c4-46be-b92d-5e045232b2d9"]
title = "Dashity Dash Dash"

app = dash.Dash(__name__)
app.layout = dash.html.Div(children=[
    dash.html.H1(children='Ted The Precocious Dash App'),

    dash.html.Div(children='''
        HISE: It's what's for dinner.
    '''),

    dash.dcc.Graph(
        id='a-first-graph',
        figure=fig_scatter,
    ),

    dash.html.Div(children='''
        HISE: All yr base r belong to us
    '''),
    
    dash.dcc.Graph(
        id='a-second-graph',
        figure=fig_box
    )
])

print(app.layout)
res = hp.freeze_dash_app(app, 
                         study_space_id = ss[0]['id'], 
                         title = title, 
                         input_file_ids = files_that_definitely_contributed_to_this_app)
print(res)


