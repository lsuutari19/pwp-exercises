from flask import Flask, request
from math import radians, sin, cos, tan
app = Flask("hello")

@app.route("/")
def index():
    # basic introduction to the routing system present
    return "How to use: we have many endpoint URLs that you can call some of them are: \n /hello/ and /trig/<sin, cos or tan>/?angle=<float>/unit=<radian or degree>"

@app.route("/hello/")
def hello():
    # basic sanity check
    try:
        name = request.args["name"]
    except KeyError:
        return "Missing query parameter: name", 400
    return f"Hello {name}"

@app.route("/trig/<func>/")
def trig(func):
    """
        Here you have multiple routing options; sin, cos and tan.
        Usage:
            -each route requires one of the functions mentioned above'
            -give an angle
            -give an unit (defaults to radians) --> if degree it will be converted to radians
        Example:
            localhost:5000/trig/sin/?angle=90&unit=degree
            localhost:5000/trig/cos/?angle=3.14
    """

    # first make sure that an angle is given, if not return 400
    functions = ["sin", "cos", "tan"]
    try:
        angle = float(request.args.get("angle"))
    except TypeError:
        return "400: Missing query parameter: angle"
    except ValueError:
        return "400: Invalid query parameter value(s)"

    unit = str(request.args.get("unit"))

    # check that the function exists if not return 404
    # and check that the unit is either "radian" or "degree" if not return 400
    # default unit to radian if nothing given
    if(func not in functions):
        return "404: Operation not found"
    if(unit != "None"):
        print("got here!", unit)
        if(unit != "radian" and unit != "degree"):
            return "400: Invalid query parameter value(s)"
        if(unit == "degree"):
            angle = radians(angle)
    if not(unit):
        unit = "radian"
    
    # return the result of the calculation
    if(func == "sin"):
        return f"200: {round(sin(angle), 3)}"
    if(func == "cos"):
        return f"200: {round(cos(angle), 3)}"
    if(func == "tan"):
        return f"200: {round(tan(angle), 3)}"
