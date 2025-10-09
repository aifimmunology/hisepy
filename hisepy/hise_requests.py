import requests
from hisepy.auth import get_bearer_token_header
import json


def parse_hise_response(resp):
    obj = None
    try:
        obj = json.loads(resp.text)
        if "Errors" in obj and len(obj["Errors"]) > 0:
            msg = obj["Errors"][0]["Message"]
        else:
            msg = resp.reason
    except:
        msg = resp.reason

    if resp.status_code != 200:
        raise SystemError(
            "%s request to %s returned with status %d. %s" %
            (resp.request.method, resp.url, resp.status_code, msg))
    return obj


def hise_post(url: str, data: dict | None = None, files: dict | None = None):
    return parse_hise_response(
        requests.post(url,
                      data=data,
                      files=files,
                      headers=get_bearer_token_header()))


def hise_get(url: str):
    return parse_hise_response(
        requests.get(url, headers=get_bearer_token_header()))
