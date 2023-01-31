from math import radians, sin, cos, tan
from flask import Flask, request
app = Flask("hello")


@app.route("/")
def index():
    # basic introduction to the routing system present
    return "To use call /trig/<func>/ endpoint"

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

    error_msg = ""
    error_flag = 0

    # first make sure that an angle is given, if not return 400
    functions = ["sin", "cos", "tan"]
    try:
        angle = float(request.args.get("angle"))
    except TypeError:
        error_msg = "Missing query parameter: angle"
        error_flag = 1
    except ValueError:
        error_msg = "Invalid query parameter value(s)"
        error_flag = 1

    if error_flag == 1:
        return error_msg, 400
    unit = str(request.args.get("unit"))

    # check that the function exists if not return 404
    # and check that the unit is either "radian" or "degree" if not return 400
    # default unit to radian if nothing given
    if func not in functions:
        return "Operation not found", 404
    if unit != "None":
        if unit not in ("radian", "degree"):
            return "Invalid query parameter value(s)", 400
        if unit == "degree":
            angle = radians(angle)
    if not unit:
        unit = "radian"

    # return the result of the calculation
    if func == "sin":
        result = round(sin(angle), 3)
    if func == "cos":
        result = round(cos(angle), 3)
    if func == "tan":
        result = round(tan(angle), 3)
    return f"200: {result}"
