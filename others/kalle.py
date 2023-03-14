import json
from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from flask_restful import Api, Resource

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///test.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
api = Api(app)

# needed to add this so the db can be created from python terminal
app.app_context().push()

class StorageItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    qty = db.Column(db.Integer, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"))
    location = db.Column(db.String(65), nullable=False)
    product = db.relationship("Product", back_populates="in_storage")

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    handle = db.Column(db.String(64), unique=True, nullable=False)
    weight = db.Column(db.Float, nullable=False)
    price = db.Column(db.Float, nullable=False)
    in_storage = db.relationship("StorageItem", back_populates="product")

class ProductCollection(Resource):
    def post(self):
        try:
            handle = request.json["handle"]
            weight = float(request.json["weight"])
            price = float(request.json["price"])
            product = Product(
                handle=handle,
                weight=weight,
                price=price
            )
            db.session.add(product)
            db.session.commit()
        except ValueError:
            return "Weight and price must be numbers", 400
        return "", 201


    def get(self):

        response_data = []
        products = Product.query.all()
        """
        for product in products:
            response_data.append([product.handle, product.weight,
            product.price, product.inventory])
        """
        return products

db.create_all()
api.add_resource(ProductCollection, "/api/products/")
app.run(debug=True)
