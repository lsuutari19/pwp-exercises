rompt["required"])

        req = prompt["required"]
        for i in req:
            if i in prompt["properties"]:
                name = input(f'{prompt["properties"][i]["description"]}:')
                if prompt["properties"][i]["type"] == "string":
                    data[name] = str(name)
                if prompt["properties"][i]["type"] == "number":
                    data[name] = float(name)   
                if prompt["properties"][i]["type"] == "integer":
                    data[name] = int(name)
        
        response = submit_data(s, body["@controls"]["senhub:add-sensor"], data)