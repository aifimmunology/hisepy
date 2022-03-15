import dash
import plotly.express as px
import pandas as pd
import hisepy
import flask
import pathlib
import os

app = dash.Dash(__name__)

# assume you have a "long-form" data frame
# see https://plotly.com/python/px-arguments/ for more options
df = pd.DataFrame({
    "Fruit": ["Apples", "Oranges", "Bananas", "Apples", "Oranges", "Bananas"],
    "Amount": [4, 1, 2, 2, 4, 5],
    "City": ["SF", "SF", "SF", "Montreal", "Montreal", "Montreal"]
})

file_list = ["0fb06e51-74c4-46be-b92d-5e045232b2d9",
             "93ea6cb8-a45f-4370-bbfe-d57ba6420882",
             "9f9dbd27-2861-4600-9920-729dbcbd61da",
             "166a161c-b615-4476-b648-86701ae7230b",
             "07104c6c-80c2-415e-a906-8ba78e5c1936"]
fig = px.bar(df, x="Fruit", y="Amount", color="City", barmode="group")
spaces = hisepy.get_study_spaces()
save_data = hisepy.save_visualization(fig,
                                      title = "Save a freaking visualization",
                                      study_space_id = spaces[0]["id"],
                                      input_file_ids = file_list)

print(save_data)
fakity_fake_file = "/tmp/fake.csv"
with open(fakity_fake_file, "w") as f:
    f.write("stuff,things,other unrelated stuff")
    f.write("stoat,stoat,a thing that is not a stoat")
    f.close()
    
fake_upload = hisepy.upload_files([fakity_fake_file],
                                  title = "Save a freaking visualization",
                                  study_space_id = spaces[0]["id"],
                                  input_file_ids = file_list)
print(fake_upload)
os.remove(fakity_fake_file)

app.layout = dash.html.Div(children=[
    dash.html.H1(children='Hello Dash'),

    dash.html.Div(children='''
        Dash: A web application framework for your data.
    '''),

    dash.dcc.Graph(
        id='from-code',
        figure=fig
    ),

    dash.html.Div(children='''
        HISE: All yr base r belong to us
    '''),
    
    dash.dcc.Graph(
        id='from-hise',
        figure=hisepy.load_visualization(save_data["trace_id"]))

])

app.run_server(debug=True)

