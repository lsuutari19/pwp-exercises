import json
import requests

API_URL = ""
data = {}

def prompt_from_schema(session, controls):
    """
    hello i just want points
    """
    if "schema" in controls:
        schema = controls["schema"]
    else:
        schema_url = controls["schemaUrl"]
        response = session.get(schema_url)
        schema = response.json()
    req = schema["required"]
    for i in req:
        if i in schema["properties"]:
            name = input(f'{schema["properties"][i]["description"]}:')
            if schema["properties"][i]["type"] == "string":
                data[i] = str(name)
            if schema["properties"][i]["type"] == "number":
                data[i] = float(name)
            if schema["properties"][i]["type"] == "integer":
                data[i] = int(name)
    response = submit_data(session, controls, data)
    return response

def submit_data(sus, ctrl, data):
    """
    hello i just want points
    """
    resp = sus.request(
        ctrl["method"],
        API_URL + ctrl["href"],
        data=json.dumps(data),
        headers = {"Content-type": "application/json"}
    )
    return resp

if __name__ == "__main__":
    with requests.Session() as s:
        resp = s.get(API_URL)
        body = resp.json()
        prompt_from_schema(s, body["@controls"])
