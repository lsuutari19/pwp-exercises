from flask import Flask, request
app = Flask("hello")

@app.route("/")
def index():
    return "How to use: we have many endpoint URLs that you can call some of them are: \n asd"

@app.route("/hello/")
def hello():
    try:
        name = request.args["name"]
    except KeyError:
        return "Missing query parameter: name", 400
    return f"Hello {name}"

@app.route("/add/<float:number_1>/<float:number_2>/")
def plus(number_1, number_2):
    return f"The result of the addition is {float(number_1) + float(number_2)}"

@app.route("/sub/<float:number_1>/<float:number_2>/")
def minus(number_1, number_2):
    return f"The result of the substraction is {float(number_1) - float(number_2)}"

@app.route("/mul/<float:number_1>/<float:number_2>/")
def mul(number_1, number_2):
    return f"The result of the multiplying is {float(number_1) * float(number_2)}"

@app.route("/div/<float:number_1>/<float:number_2>/")
def div(number_1, number_2):
    if(number_2 == 0.0):
        return "NaN"
    return f"The result of the substraction is {float(number_1) / float(number_2)}"

