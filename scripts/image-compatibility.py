import plotly.graph_objects as go
import requests

import hisepy

trace_id = "25d7f47a-183f-4894-83a7-28cd472b9dd0"

layout = hisepy.reader.parse_hise_response(
    requests.request("GET",
                     hisepy.reader.hise_url("toolchain", "visualization_path",
                                            trace_id),
                     headers=hisepy.auth.get_bearer_token_header()))
layout["layout"].pop("margin")
layout["layout"].pop("autocolorscale")
fig = go.Figure(layout)
tr = hisepy.get_trace(trace_id)
for d in hisepy.load_visualization_data(tr["steps"]["dataReference"]):
    d.pop("xField")
    d.pop("yField")
    d["marker"].pop("color")
    d["marker"].pop("size")
    fig.add_trace(d)

fig.show()

fixed = hisepy.load_visualization(trace_id)
fixed.show()
