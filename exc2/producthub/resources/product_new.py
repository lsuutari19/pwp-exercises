from flask import Flask, request, Response
from flask_restful import Api, Resource
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import NotFound
from werkzeug.routing import BaseConverter


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///test.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
api = Api(app)

app.app_context().push()


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


class ProductCollection(Resource):
    """
        Contains methods for GET and POST of products
        POST creates a object with handle, weight and price
    """

    def get(self):
        return Response(status=501)

    def post(self):
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
        response.headers["location"] = api.url_for(ProductCollection, Location=handle)
        return response

class ProductConverter(BaseConverter):

    def to_python(self, product_name):
        db_product = Product.query.filter_by(handle=product_name).first()
        if db_product is None:
            raise NotFound
        return db_product
        
    def to_url(self, db_product):
        return db_product.handle


app.url_map.converters["product"] = ProductConverter
api.add_resource(ProductCollection, "/api/products/<product:product>")

#api.add_resource(ProductCollection, "/api/products/")
app.run(debug=True)
