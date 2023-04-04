import requests
import json


API_URL = "https://pwpcourse.eu.pythonanywhere.com"

def check_cheese(value):
    if "cheese" in str(value):
        print("Cheese is in room", value["handle"])
        return True
    return False

def get_hrefs(body):
    maze_rooms_href = []
    for i in body["@controls"]:
        if "self" in i:
            pass
        else:
            maze_rooms_href.append(body["@controls"][i]["href"])
    return maze_rooms_href

def prompt_from_schema(session, controls):
    # requests session object - you must use this object to make any requests
    # Mason hypermedia control as a dictionary
    print(session, controls)
    if "schema" in controls:
        schema = controls["schema"]
        for name, props in schema["properties"].items():
            local_name = mapping[name]
            value = getattr(tag, local_name)
            if value is not None:
                value = convert_value(value, props)
                body[name] = value

    return ""

if __name__ == "__main__":
    API_URL = "http://localhost:5000"
    with requests.Session() as s:
        resp = s.get(API_URL + "/api/sensors/")
        body = resp.json()
        prompt_from_schema(s, body["@controls"]["senhub:add-sensor"])



def request_session():
    with requests.Session() as s:
        with requests.Session() as s:
            s.headers.update({"Accept": "application/vnd.mason+json"})
            resp = s.get(API_URL + "/api/")
            if resp.status_code != 200:
                print("Unable to access API.")
            else:
                body = resp.json()
                maze_href = body["@controls"]["maze:entrance"]["href"]
            print(maze_href)
            
            resp = s.get(API_URL + maze_href)
            body = resp.json()
            check_cheese(body)
            print(body)
            
            already_visited = []
            while True:
                maze_rooms_href = []
                maze_rooms_href = get_hrefs(body)
                #print(maze_rooms_href)

                for room in maze_rooms_href:
                    if room in already_visited:
                        pass
                    else:
                        resp = s.get(API_URL + room)
                        body= resp.json()
                        print("Examining room:", body["handle"])
                        #print(body)
                if check_cheese(body):
                    break
                else:
                    already_visited.append(room)
            


