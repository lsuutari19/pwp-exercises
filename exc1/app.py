import json
from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine
from sqlalchemy import event

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///test.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
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


db.create_all()


@app.route("/products/add/", methods=["POST"])
def add_product():

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
    return "", 201


@app.route("/storage/<handle>/add/", methods=["POST"])
def add_to_storage(handle):
    try:
        loc = request.json["location"]
        quant = request.json["qty"]
    except KeyError:
        return "Incomplete request - missing fields", 400
    try:
        int(quant)
    except ValueError:
        return "Qty must be an integer", 400
    product = Product.query.filter_by(handle=handle).first()
    if not product:
        return "Product not found", 404
    storage_entry = StorageItem(
        product_id=product.id,
        qty=quant,
        location=loc
    )
    db.session.add(storage_entry)
    db.session.commit()
    return "", 201


@app.route("/storage/", methods=["GET", "POST"])
def get_inventory():
    if request.method == "POST":
        return "", 405
    inventory = StorageItem.query.all()
    items = {}
    for item in inventory:
        handle = item.product.handle
        if handle not in items:
            items[handle] = {
                "handle": handle,
                "weight": item.product.weight,
                "price": item.product.price,
                "inventory": []
            }
        items[handle]["inventory"].append((item.location, item.qty))

    return json.dumps(list(items.values()), sort_keys=False), 200
