import json
import click
from jsonschema import validate, ValidationError
from flask import Flask, Response, request
from flask.cli import with_appcontext
from flask_sqlalchemy import SQLAlchemy
from flask_restful import Resource, Api
from sqlalchemy.exc import IntegrityError, StatementError
from werkzeug.exceptions import NotFound
from werkzeug.routing import BaseConverter

app = Flask(__name__)
app.config["SERVER_NAME"] = "localhost"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///test.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

api = Api(app)

MASON = "application/vnd.mason+json"
ERROR_PROFILE = "/profiles/error/"
LINK_RELATIONS_URL = "/storage/link-relations/"
PRODUCT_PROFILE = "/profiles/product/"

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    handle = db.Column(db.String(64), unique=True, nullable=False)
    price = db.Column(db.Float, nullable=False)
    weight = db.Column(db.Float, nullable=False)

    storage = db.relationship("StorageItem", back_populates="product")

    @staticmethod
    def json_schema():
        pass

class StorageItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    qty = db.Column(db.Integer, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    location = db.Column(db.String(64), nullable=False)

    product = db.relationship("Product", back_populates="storage")


class MasonBuilder(dict):
    """
    A convenience class for managing dictionaries that represent Mason
    objects. It provides nice shorthands for inserting some of the more
    elements into the object but mostly is just a parent for the much more
    useful subclass defined next. This class is generic in the sense that it
    does not contain any application specific implementation details.
    """

    def add_error(self, title, details):
        """
        Adds an error element to the object. Should only be used for the root
        object, and only in error scenarios.

        Note: Mason allows more than one string in the @messages property (it's
        in fact an array). However we are being lazy and supporting just one
        message.

        : param str title: Short title for the error
        : param str details: Longer human-readable description
        """

        self["@error"] = {
            "@message": title,
            "@messages": [details],
        }

    def add_namespace(self, ns, uri):
        """
        Adds a namespace element to the object. A namespace defines where our
        link relations are coming from. The URI can be an address where
        developers can find information about our link relations.

        : param str ns: the namespace prefix
        : param str uri: the identifier URI of the namespace
        """

        if "@namespaces" not in self:
            self["@namespaces"] = {}

        self["@namespaces"][ns] = {
            "name": uri
        }

    def add_control(self, ctrl_name, href, **kwargs):
        """
        Adds a control property to an object. Also adds the @controls property
        if it doesn't exist on the object yet. Technically only certain
        properties are allowed for kwargs but again we're being lazy and don't
        perform any checking.

        The allowed properties can be found from here
        https://github.com/JornWildt/Mason/blob/master/Documentation/Mason-draft-2.md

        : param str ctrl_name: name of the control (including namespace if any)
        : param str href: target URI for the control
        """

        if "@controls" not in self:
            self["@controls"] = {}

        self["@controls"][ctrl_name] = kwargs
        self["@controls"][ctrl_name]["href"] = href


class InventoryBuilder(MasonBuilder):

    pass


class ProductConverter(BaseConverter):

    pass


class ProductCollection(Resource):

    def get(self):
        products = Product.query
        body = []
        for product in products:
            body.append({
                "handle": product.handle,
                "price": product.price,
                "weight": product.weight
            })
        return body

    def post(self):
        try:
            data = request.json
            handle = data["handle"]
            weight = float(data["weight"])
            price = float(data["price"])
            product = Product(
                handle=handle,
                weight=weight,
                price=price
            )
            db.session.add(product)
            db.session.commit()
        except KeyError:
            return "Incomplete request - missing fields", 400
        except TypeError:
            return "Request content type must be JSON", 415
        except ValueError:
            return "Weight and price must be numbers", 400
        except IntegrityError:
            return "Handle already exists", 409
        except StatementError:
            return "", 500
        return Response(status=201, headers={"Location": api.url_for(ProductItem, product=product)})


class ProductItem(Resource):

    def get(self, product):
        body ={
            "handle": product.handle,
            "weight": product.weight,
            "price": product.price
        }
        return body

    def put(self, product):
        if not request.json:
            return "Unsupported media type - Requests must be JSON", 415

        try:
            validate(request.json, Product.json_schema())
        except ValidationError as e:
            return f"Invalid JSON document: {e}", 400

        product.handle = request.json["handle"]
        product.price = float(request.json["price"])
        product.weight = float(request.json["weight"])

        try:
            db.session.commit()
        except IntegrityError:
            return f"Product with handle '{product.handle}' already exists.", 409


        return Response(status=204)

    def delete(self, product):
        db.session.delete(product)
        db.session.commit()

        return Response(status=204)



@click.command("init-db")
@with_appcontext
def init_db_command():
    """
    Initializes the database. If already initialized, nothing happens.
    """

    db.create_all()

@click.command("populate-db")
@with_appcontext
def populate_db_command():
    """
    Populates the database with products
    """

    for i in range(1, 4):
        p = Product(
            handle="test-product-{}".format(i),
            price=10.5 * i,
            weight=2.1 * i
        )
        db.session.add(p)
    db.session.commit()

@click.command("test-document")
@with_appcontext
def test_document_command():
    with app.app_context():
        product = Product.query.first()
    document = InventoryBuilder()
    document.add_control_all_products()
    document.add_control_add_product()
    document.add_control_delete_product(product)
    document.add_control_edit_product(product)

app.url_map.converters["product"] = ProductConverter
api.add_resource(ProductCollection, "/api/products/")
api.add_resource(ProductItem, "/api/products/<product:product>/")
app.cli.add_command(init_db_command)
app.cli.add_command(populate_db_command)
app.cli.add_command(test_document_command)

#print("Starting SensorHub flask app...\n\n")
#app.run(debug=True)
