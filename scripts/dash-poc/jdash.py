from jupyter_dash import JupyterDash
import hisepy as hp
import os
import dash
from dash import html, dcc
from dash import dash_table
# import dash_bio as dashbio
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from dash.dependencies import Input, Output
import pandas as pd
import socket
from jupyter_dash.comms import _send_jupyter_config_comm_request

_send_jupyter_config_comm_request()
JupyterDash.infer_jupyter_proxy_config()

file_list = ["0fb06e51-74c4-46be-b92d-5e045232b2d9",
             "93ea6cb8-a45f-4370-bbfe-d57ba6420882",
             "9f9dbd27-2861-4600-9920-729dbcbd61da",
             "166a161c-b615-4476-b648-86701ae7230b",
             "07104c6c-80c2-415e-a906-8ba78e5c1936"]
cyto_dict_df = hp.read_files(file_list = file_list, query_id=None, query_dict=None, to_df=True)
cyto_dict_df_merged = pd.merge(cyto_dict_df['labResults'], cyto_dict_df['descriptors'], left_on='sampleKitGuid', right_on='sample.sampleKitGuid')
pop_stats_file = 'cache/B007/population-stats.csv'
file_df = pd.read_csv(pop_stats_file)
descriptive = cyto_dict_df_merged[['subject.biologicalSex',
                                   'subject.ethnicity',
                                   'subject.race']].describe(include = [object])
external_stylesheets = ['https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css']

app = JupyterDash(__name__, external_stylesheets=external_stylesheets)

# Create server variable with Flask server object for use with gunicorn
server = app.server

# cyto pop stats data
# find the correct path - this is a temporary work around

bar_mode_options = options=['group','stack', 'overlay', 'relative']

# save happens here
app.layout = html.Div([
    html.Div(className='container'),
    
    html.H2(className = 'my-3', children='''Cytometry: Population Stats File(s)'''),
    
    html.Div(className='row mb-5 rounded border border-light', children=[
        html.Div(className='col', children=[
            html.H5(className='text-secondary', children=['Descriptive Statistics']),
            html.P(className='text-muted', children=['Descriptive statistics for the population count column']),
            dash_table.DataTable(
                id='table22',
                columns=[{"name": i, "id": i} for i in descriptive.columns],
                data=descriptive.to_dict('records'),
                page_size=10,
            )
        ])
    ]),
    
    html.Div(className='row mb-5 rounded border border-light', children=[
        html.Div(className='col', children=[
            html.H5(className='text-secondary', children=['Data Table']),
            html.P(className='text-muted', children=['Table view of the flow cytometry population stats counts. The list of columns and the types of those columns in the schema.']),
            dash_table.DataTable(
                id='table',
                columns=[{"name": i, "id": i} for i in cyto_dict_df_merged.columns],
                data=file_df.to_dict('records'),
                # data=cyto_dict_df_merged.to_dict('records'),
                page_size=10,
            )
        ])
    ]),
    
    html.Div(className='row mb-5 rounded border border-light', children=[
        html.Div(className='col-4', children=[
            html.H5(className='text-secondary', children=['Figure Layout']),
            html.P(className='text-muted', children=['Change plot layout']),
            dcc.Dropdown(
                id='bar-mode',
                options=[{'label': i, 'value': i} for i in bar_mode_options],
                value='group'
            ),
        ]),
    ]),
    
    html.Div(className='row mb-5 rounded border border-light', children=[
        html.Div(className='col', children=[
            html.H5(className='text-secondary', children=['Cyto Plot']),
            html.P(className='text-muted', children=['Plot of Cytometry Population Stats']),
            html.Div(className="form-control", children=[
                dcc.Graph(id='cyto-graph')
            ])
        ]),
    ]),
    
    html.Div(className='row mb-5 rounded border border-light', children=[
        html.Div(className='col', children=[
            html.H5(className='text-secondary', children=['SPLOM']),
            html.P(className='text-muted', children=['Multiple Dimension']),
            html.Div(className="form-control", children=[
                dcc.Graph(id='cyto-splom')
            ])
        ]),
    ]),
    
    # html.Div(className='row mb-5 rounded border border-light', children=[
    #     html.Div(className='col', children=[
    #         html.H5(className='text-secondary', children=['Volcano Plot']),
    #         html.P(className='text-muted', children=['Volcano Plot with effects range slider']),
    #         html.Div(className="form-control", children=[
    #             'Effect sizes',
    #             dcc.RangeSlider(
    #                 id='default-volcanoplot-input',
    #                 min=-3,
    #                 max=3,
    #                 step=0.05,
    #                 marks={i: {'label': str(i)} for i in range(-3, 3)},
    #                 value=[-0.5, 1]
    #             ),
    #             html.Br(),
    #             html.Div(
    #                 dcc.Graph(
    #                     id='dashbio-default-volcanoplot',
    #                     figure=dashbio.VolcanoPlot(
    #                         dataframe=cyto_dict_df_merged
    #                     )
    #                 )
    #             )
    #         ])
    #     ]),
    # ]),
])

@app.callback(
    Output('cyto-graph', 'figure'),
    Output('cyto-splom', 'figure'),
    Input('bar-mode', 'value'))
def update_graph(bar_mode_name):
    # fig = px.bar(cyto_dict_df_merged, x="Population", y="Count", color='subject.subjectGuid')
    fig = px.bar(file_df, x="Population", y="Count")
    
    fig.update_layout(
        barmode=bar_mode_name,
        legend_title_text='Subject ID',
        autosize=True,
        height=640,
        yaxis=dict(
            title_text="Population Count",
        ),
        xaxis=dict(
            title_text="Population",
        )
    )

    fig.update_yaxes(automargin=True)
    fig.update_xaxes(automargin=True)
    
    splom_fig = px.scatter_matrix(file_df)
        # dimensions=['subject.biologicalSex', 'subject.ethnicity', 'subject.race'],
        # color="subjectGuid")

    splom_fig.update_layout(
        legend_title_text='Subject ID',
        autosize=True,
        height=800,
        yaxis=dict(
            title_text="Population Count",
        ),
        xaxis=dict(
            title_text="Population",
        ))
    
    # volcano_fig = dashbio.VolcanoPlot(
    #     dataframe=cyto_dict_df_merged,
    #     genomewideline_value=2.5,
    #     effect_size_line=effects
    # )
    
    return fig, splom_fig

ss = hp.get_study_spaces()
save_dash_app_result = hp.save_dash_app(app, 
                                        study_space_id=ss[0]['id'], 
                                        title="Work, I Beseech Thee", 
                                        input_file_ids=file_list)
print(save_dash_app_result)
