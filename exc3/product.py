import sys
import json
from flask import Flask, request, Response
from flask_restful import Api, Resource
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.engine import Engine
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import NotFound, Conflict, BadRequest, UnsupportedMediaType
from jsonschema import validate, ValidationError, draft7_format_checker
JSON = "application/json"

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///test.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
api = Api(app)

app.app_context().push()

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

class StorageItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"))
    qty = db.Column(db.Integer, nullable=False)
    location = db.Column(db.String(64), nullable=False)

    product = db.relationship("Product", back_populates="in_storage")


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    handle = db.Column(db.String(64), unique=True, nullable=False)
    weight = db.Column(db.Float, nullable=False)
    price = db.Column(db.Float, nullable=False)

    in_storage = db.relationship("StorageItem", back_populates="product")
    
    def serialize(self):
        return {
            "handle": self.handle,
            "weight": self.weight,
            "price": self.price
        }

    @staticmethod
    def json_schema():
        schema = {
            "type": "object",
            "required": ["handle", "weight", "price"]
        }
        props = schema["properties"] = {}
        props["handle"] = {
            "description": "Product's unique handle",
            "type": "string"
        }
        props["weight"] = {
            "description": "Product's weight",
            "type": "number"
        }
        props["price"] = {
            "description": "Product's price",
            "type": "number"
        }
        return schema
    


class ProductCollection(Resource):
    """
        Contains methods for GET and POST of products
        POST creates a object with handle, weight and price
    """

    def get(self):
        body = {"products": []}
        for product in Product.query.all():
            item = product.serialize()
            body["products"].append(item)
        return Response(json.dumps(body), 200, mimetype=JSON)

    def post(self):
        if not request.json:
            return "", 415
        
        try:
            validate(request.json, Product.json_schema(),
                    format_checker=draft7_format_checker)
        except ValidationError as exc:
            raise BadRequest(description=str(exc)) from exc
        
        try:
            handle = request.json["handle"]
            weight = request.json["weight"]
            price = request.json["price"]
        except KeyError:
            return "Incomplete request - missing fields", 400
        
        try:
            float(weight)
            float(price)
        except ValueError:
            return "Weight and price must be numbers", 400

        product_entry = Product(
            handle=handle,
            weight=weight,
            price=price,
        )
        try:
            db.session.add(product_entry)
            db.session.commit()
        except IntegrityError:
            return "Handle already exists", 409
        response = Response(status=201)
        print(handle)
        response.headers["location"] = api.url_for(ProductItem, product=handle)
        return response

class ProductItem(Resource):

    def get(self, product):
        pass

    def put(self, product):
        pass
    
    def delete(self, product):
        pass

db.create_all()


api.add_resource(ProductCollection, "/api/products/")
api.add_resource(ProductItem, "/api/products/<product>")
app.run(debug=True)