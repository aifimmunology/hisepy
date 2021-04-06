import requests
import os

metadata_server_root = "http://metadata.google.internal/computeMetadata/v1/instance"
instance_name_path = "name"
client_id_path = "attributes/iap-client-id"
identity_path = "service-accounts/default/identity"
server_id_path = "attributes/hise-server"
token_env = "TOKEN_GENERATOR"

default_metadata = {
    instance_name_path: "local-testing-instance",
    client_id_path: "REDACTED_GCP_CLIENT_ID",
    server_id_path: "dev.allenimmunology.org"
}

def get_from_metadata_server(path):
    value = None
    try:
        resp = requests.request("GET",
                                "%s/%s" % (metadata_server_root, path),
                                headers = {"Metadata-Flavor": "Google"})
        if resp.status_code != 200:
            raise(SystemError("Request to %s failed with status %d. %s" %
                              (path,resp.status_code,resp.text)))
        value = resp.text
    except:
        if path in default_metadata:
            print("Returning default value for %s" % (path))
            value = default_metadata[path]
        else:
            raise(SystemError("No default value found for %s. Cannot continue" % path))
    return value

def get_bearer_token_header():
    client_id = get_from_metadata_server(client_id_path)
    token_gen = os.getenv(token_env)
    if token_gen is not None:
        return {"Authorization": "Bearer %s" % os.popen(token_gen).read().rstrip()}
        
    return {"Authorization": "Bearer %s" %
            (get_from_metadata_server("%s?format=full&audience=%s" %
                                      (identity_path, client_id)))}

