from flask import Blueprint
from flask_restful import Resource, Api

api_bp = Blueprint("api", __name__, url_prefix="/api")
api = Api(api_bp)

# this import must be placed after we create api to avoid issues with
# circular imports
from producthub.resources.product import ProductCollection

api.add_resource(ProductCollection, 
    "/products/",
    "/products/handle"
)

@api_bp.route("/")
def index():
    return ""
