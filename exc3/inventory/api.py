import json
import click
from jsonschema import validate, ValidationError
from flask import Flask, Response, request, url_for
from flask.cli import with_appcontext
from flask_sqlalchemy import SQLAlchemy
from flask_restful import Resource, Api
from sqlalchemy.exc import IntegrityError, StatementError
from werkzeug.exceptions import NotFound
from werkzeug.routing import BaseConverter

app = Flask(__name__)
app.config["SERVER_NAME"] = "127.0.0.1:5000"
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
        schema = {
            "type": "object",
            "properties": {},
            "required": ["handle", "price", "weight"]
        }
        props = schema["properties"]
        props["handle"] = {
            "description": "Products unique handle",
            "type": "string"
        }
        props["price"] = {
            "description": "Products price",
            "type": "number"
        }
        props["weight"] = {
            "description": "Products weight",
            "type": "number"
        }
        return schema


class StorageItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    qty = db.Column(db.Integer, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey(
        "product.id"), nullable=False)
    location = db.Column(db.String(64), nullable=False)

    product = db.relationship("Product", back_populates="storage")


class ProductConverter(BaseConverter):

    def to_python(self, product_name):
        db_product = Product.query.filter_by(handle=product_name).first()
        if db_product is None:
            raise NotFound
        return db_product

    def to_url(self, db_product):
        return db_product.handle


class MasonBuilder(dict):
    """
    A convenience class for managing dictionaries that represent Mason
    objects. It provides nice shorthands for inserting some of the more
    elements into the object but mostly is just a parent for the much more
    useful subclass defined next. This class is generic in the sense that it
    does not contain any application specific implementation details.

    Note that child classes should set the *DELETE_RELATION* to the application
    specific relation name from the application namespace. The IANA standard
    does not define a link relation for deleting something.
    """

    DELETE_RELATION = ""

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

    def add_control_post(self, ctrl_name, title, href, schema):
        """
        Utility method for adding POST type controls. The control is
        constructed from the method's parameters. Method and encoding are
        fixed to "POST" and "json" respectively.

        : param str ctrl_name: name of the control (including namespace if any)
        : param str href: target URI for the control
        : param str title: human-readable title for the control
        : param dict schema: a dictionary representing a valid JSON schema
        """

        self.add_control(
            ctrl_name,
            href,
            method="POST",
            encoding="json",
            title=title,
            schema=schema
        )

    def add_control_put(self, title, href, schema):
        """
        Utility method for adding PUT type controls. The control is
        constructed from the method's parameters. Control name, method and
        encoding are fixed to "edit", "PUT" and "json" respectively.

        : param str href: target URI for the control
        : param str title: human-readable title for the control
        : param dict schema: a dictionary representing a valid JSON schema
        """

        self.add_control(
            "edit",
            href,
            method="PUT",
            encoding="json",
            title=title,
            schema=schema
        )

    def add_control_delete(self, title, href):
        """
        Utility method for adding PUT type controls. The control is
        constructed from the method's parameters. Control method is fixed to
        "DELETE", and control's name is read from the class attribute
        *DELETE_RELATION* which needs to be overridden by the child class.

        : param str href: target URI for the control
        : param str title: human-readable title for the control
        """

        self.add_control(
            "mumeta:delete",
            href,
            method="DELETE",
            title=title,
        )

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


class InventoryBuilder(MasonBuilder):

    def add_control_all_products(self):
        self.add_control(
            "storage:products-all",
            api.url_for(ProductCollection),
            title="All products",
            method="GET"
        )

    def add_control_delete_product(self, handle):
        self.add_control(
            "storage:delete",
            api.url_for(ProductItem, product=handle),
            method="DELETE"
        )

    def add_control_add_product(self):
        self.add_control_post(
            "storage:add-product",
            "Add a new product",
            api.url_for(ProductCollection),
            Product.json_schema()
        )

    def add_control_edit_product(self, handle):
        self.add_control_put(
            "edit",
            api.url_for(ProductItem, product=handle),
            Product.json_schema(),
        )


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


@app.route("/api/")
def api_entry_point():
    body = InventoryBuilder()
    body.add_namespace("storage", LINK_RELATIONS_URL)
    body.add_control_all_products()
    return Response(json.dumps(body), 200, mimetype=MASON)


@app.route("/")
def index():
    return "How to1:"


@app.route("/products/link-relations/")
def link_relations():
    return "here be link relations"


@app.route("/profiles/product/")
def profiles():
    return "How to3:"


@app.route("/profiles/error-profile/")
def profiles_error():
    return "error-profile"


class ProductCollection(Resource):

    def get(self):

        body = InventoryBuilder(items=[])
        body.add_namespace("storage", LINK_RELATIONS_URL)
        body.add_control("self", href=api.url_for(ProductCollection))
        body.add_control_add_product()

        for product in Product.query.all():
            item = {
                "handle": product.handle,
                "weight": product.weight,
                "price": product.price,

            }
            item["@controls"] = {
                "self": {"href": api.url_for(ProductItem, product=product)},
                "profile": {"href": PRODUCT_PROFILE}
            }
            body["items"].append(item)
        return Response(json.dumps(body), 200, mimetype=MASON)

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
        product_information = {
            "handle": product.handle,
            "weight": product.weight,
            "price": product.price
        }
        body = InventoryBuilder(product_information)
        body.add_namespace("storage", LINK_RELATIONS_URL)
        body.add_control("self", href=api.url_for(
            ProductItem, product=product))
        body.add_control("profile", href=PRODUCT_PROFILE)
        body.add_control("collection", href=api.url_for(ProductCollection))
        body.add_control_edit_product(product)
        body.add_control_delete_product(product)
        return Response(json.dumps(body), 200, mimetype=MASON)

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
    document["@controls"]["collection"]
    # print(document["items"][0]["@controls"]["self"])


app.url_map.converters["product"] = ProductConverter
api.add_resource(ProductCollection, "/api/products/")
api.add_resource(ProductItem, "/api/products/<product:product>/")
app.cli.add_command(init_db_command)
app.cli.add_command(populate_db_command)
app.cli.add_command(test_document_command)

# print("Starting SensorHub flask app...\n\n")
# app.run(debug=True)
