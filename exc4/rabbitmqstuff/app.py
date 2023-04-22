from datetime import datetime
import click
import json
import pika
from flask import Flask, Response, request
from flask.cli import with_appcontext
from flask_caching import Cache
from flask_sqlalchemy import SQLAlchemy
from flask_restful import Resource, Api
from jsonschema import validate, ValidationError, draft7_format_checker
from sqlalchemy.engine import Engine
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError, OperationalError
from werkzeug.exceptions import UnsupportedMediaType, NotFound, Conflict, BadRequest
from werkzeug.routing import BaseConverter

print("New module instance")

JSON = "application/json"
MASON = "application/vnd.mason+json"
LINK_RELATIONS_URL = "/sensorhub/link-relations/"
ERROR_PROFILE = "/profiles/error/"
SENSOR_PROFILE = "/profiles/sensor/"

app = Flask(__name__, static_folder="static")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///development.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["CACHE_TYPE"] = "FileSystemCache"
app.config["CACHE_DIR"] = "cache"
app.config["RABBITMQ_BROKER_ADDR"] = "localhost"

api = Api(app)
db = SQLAlchemy(app)
cache = Cache(app)

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

deployments = db.Table(
    "deployments",
    db.Column("deployment_id", db.Integer, db.ForeignKey("deployment.id"), primary_key=True),
    db.Column("sensor_id", db.Integer, db.ForeignKey("sensor.id"), primary_key=True)
)

class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    altitude = db.Column(db.Float, nullable=True)
    description=db.Column(db.String(256), nullable=True)
    
    sensor = db.relationship("Sensor", back_populates="location", uselist=False)

    def serialize(self, short_form=False):
        doc = {
            "name": self.name
        }
        if not short_form:
            doc["longitude"] = self.longitude
            doc["latitude"] = self.latitude
            doc["altitude"] = self.altitude
            doc["description"] = self.description
        return doc
        
    def deserialize(self, doc):
        self.name = doc["name"]
        self.latitude = doc.get("latitude")
        self.longitude = doc.get("longitude")
        self.altitude = doc.get("altitude")
        self.description = doc.get("description")
        

class Deployment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start = db.Column(db.DateTime, nullable=False)
    end = db.Column(db.DateTime, nullable=False)
    name = db.Column(db.String(128), nullable=False)
    
    sensors = db.relationship("Sensor", secondary=deployments, back_populates="deployments")


class Sensor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), nullable=False, unique=True)
    model = db.Column(db.String(128), nullable=False)
    location_id = db.Column(
        db.Integer,
        db.ForeignKey("location.id"),
        unique=True, nullable=True
    )
    
    location = db.relationship("Location", back_populates="sensor")
    measurements = db.relationship("Measurement", back_populates="sensor")
    deployments = db.relationship("Deployment", secondary=deployments, back_populates="sensors")
    stats = db.relationship("Stats", back_populates="sensor", uselist=False)

    def serialize(self, short_form=False):
        return {
            "name": self.name,
            "model": self.model,
            "location": self.location and self.location.serialize(short_form=short_form)
        }

    def deserialize(self, doc):
        self.name = doc["name"]
        self.model = doc["model"]

    @staticmethod
    def json_schema():
        schema = {
            "type": "object",
            "required": ["name", "model"]
        }
        props = schema["properties"] = {}
        props["name"] = {
            "description": "Sensor's unique name",
            "type": "string"
        }
        props["model"] = {
            "description": "Name of the sensor's model",
            "type": "string"
        }
        return schema

class Stats(db.Model):
    
    id = db.Column(db.Integer, primary_key=True)
    generated = db.Column(db.DateTime, nullable=False)
    mean = db.Column(db.Float, nullable=False)
    sensor_id = db.Column(
        db.Integer,
        db.ForeignKey("sensor.id"),
        unique=True, nullable=False
    )
    
    sensor = db.relationship("Sensor", back_populates="stats")
    
    def serialize(self):
        return {
            "generated": self.generated.isoformat(),
            "mean": self.mean
        }
    
    def deserialize(self, doc):
        self.generated = datetime.fromisoformat(doc["generated"])
        self.mean = doc["mean"]
        
    @staticmethod
    def json_schema():
        schema = {
            "type": "object",
            "required": ["generated", "mean"]
        }
        props = schema["properties"] = {}
        props["generated"] = {
            "description": "Generation timestamp",
            "type": "string",
            "format": "date-time"
        }
        props["mean"] = {
            "description": "Mean value of data",
            "type": "number"
        }
        return schema
        


class Measurement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sensor_id = db.Column(db.Integer, db.ForeignKey("sensor.id", ondelete="SET NULL"))
    value = db.Column(db.Float, nullable=False)
    time = db.Column(db.DateTime, nullable=False)
        
    sensor = db.relationship("Sensor", back_populates="measurements")


class SensorConverter(BaseConverter):
    
    def to_python(self, sensor_name):
        db_sensor = Sensor.query.filter_by(name=sensor_name).first()
        if db_sensor is None:
            raise NotFound
        return db_sensor
        
    def to_url(self, db_sensor):
        return db_sensor.name


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
            "senhub:delete",
            href,
            method="DELETE",
            title=title,
        )

class SensorhubBuilder(MasonBuilder):
    
    def add_control_add_sensor(self):
        self.add_control_post(
            "senhub:add-sensor",
            "Add sensor",
            api.url_for(SensorCollection),
            Sensor.json_schema()
        )
        
    def add_control_add_measurement(self, sensor):
        self.add_control_post(
            "senhub:add-measurement",
            "Add measurement",
            api.url_for(MeasurementCollection, sensor=sensor),
            Measurement.json_schema()
        )
        
    def add_control_delete_sensor(self, sensor):
        self.add_control_delete(
            "Delete this sensor",
            api.url_for(SensorItem, sensor=sensor)
        )
    
    def add_control_delete_stats(self, sensor):
        self.add_control_delete(
            "Delete these stats",
            api.url_for(SensorStats, sensor=sensor)
        )

    def add_control_get_measurements(self, sensor):
        self.add_control(
            "senhub:measurements",
            api.url_for(MeasurementCollection, sensor=sensor)
        )
        
    def add_control_modify_sensor(self, sensor):
        self.add_control_put(
            "Modify sensor",
            api.url_for(SensorItem, sensor=sensor),
            Sensor.json_schema()
        )
        
    def add_control_modify_stats(self, sensor):
        self.add_control_put(
            "Modify sensor",
            api.url_for(SensorStats, sensor=sensor),
            Stats.json_schema()
        )
        


class SensorCollection(Resource):
    
    def get(self):
        body = SensorhubBuilder()

        body.add_namespace("senhub", LINK_RELATIONS_URL)
        body.add_control("self", api.url_for(SensorCollection))
        body.add_control_add_sensor()
        body["items"] = []        
        for db_sensor in Sensor.query.all():
            item = SensorhubBuilder(db_sensor.serialize(short_form=True))
            body["items"].append(item)
            item.add_control(
                "self", 
                api.url_for(SensorItem, sensor=db_sensor)
            )
            item.add_control("profile", SENSOR_PROFILE)
            
        return Response(json.dumps(body), 200, mimetype=MASON)
    
    def post(self):
        if not request.json:
            raise UnsupportedMediaType
            
        try:
            validate(request.json, Sensor.json_schema())
        except ValidationError as e:
            raise BadRequest(description=str(e))

        sensor = Sensor()
        sensor.deserialize(request.json)
        
        try:
            db.session.add(sensor)
            db.session.commit()
        except IntegrityError:
            raise Conflict(
                "Sensor with name '{name}' already exists.".format(
                    **request.json
                )
            )
        
        return Response(
            status=201, headers={"Location": api.url_for(SensorItem, sensor=sensor)}
        )

    
class SensorItem(Resource):

    def get(self, sensor):
        body = SensorhubBuilder(sensor.serialize())
        body.add_namespace("senhub", LINK_RELATIONS_URL)
        body.add_control("self", api.url_for(SensorItem, sensor=sensor))
        body.add_control("profile", SENSOR_PROFILE)
        body.add_control("collection", api.url_for(SensorCollection))
        body.add_control_delete_sensor(sensor)
        body.add_control_modify_sensor(sensor)
        #body.add_control_add_measurement(sensor)
        body.add_control_get_measurements(sensor)
        body.add_control("senhub:stats", api.url_for(SensorStats, sensor=sensor))
        body.add_control("senhub:measurements-first",
            api.url_for(MeasurementCollection, sensor=sensor)
        )        
        return Response(json.dumps(body), 200, mimetype=MASON)
        
    def put(self, sensor):
        if not request.json:
            raise UnsupportedMediaType

        try:
            validate(request.json, Sensor.json_schema())
        except ValidationError as e:
            raise BadRequest(description=str(e))

        sensor.deserialize(request.json)
        try:
            db.session.add(sensor)
            db.session.commit()
        except IntegrityError:
            raise Conflict(
                "Sensor with name '{name}' already exists.".format(
                    **request.json
                )
            )
        
        return Response(status=204)

    def delete(self, sensor):
        db.session.delete(sensor)
        db.session.commit()
        return Response(status=204)
    
    
class LocationItem(Resource):
    
    def get(self, location):
        pass
    

class MeasurementItem(Resource):
    
    def delete(self, sensor, measurement):
        Measurement.query.filter_by(id=measurement).delete()
        return Response(status=204)
    

class MeasurementCollection(Resource):
    
    PAGE_SIZE = 50
    
    def get(self, sensor):
        page = int(request.args.get("page", 0))
        remaining = Measurement.query.filter_by(
            sensor=sensor
        ).order_by("time").offset(page * self.PAGE_SIZE)
        
        body = SensorhubBuilder(
            sensor=sensor.name,
            items=[]
        )
        body.add_namespace("senhub", LINK_RELATIONS_URL)
        base_uri = api.url_for(MeasurementCollection, sensor=sensor)
        body.add_control("up", api.url_for(SensorItem, sensor=sensor))
        if page >= 1:
            body.add_control("self", base_uri + f"?page={page}")
            body.add_control("prev", base_uri + f"?page={page - 1}")
        else:
            body.add_control("self", base_uri)
        if remaining.count() > self.PAGE_SIZE:
            body.add_control("next", base_uri + f"?page={page + 1}")
            
        for meas in remaining.limit(self.PAGE_SIZE):
            body["items"].append(
                {
                    "value": meas.value,
                    "time": meas.time.isoformat()
                }
            )
        return Response(json.dumps(body), 200, mimetype=MASON)

class SensorStats(Resource):

    def get(self, sensor):
        if sensor.stats:
            body = SensorhubBuilder(
                generated=sensor.stats.generated.isoformat(),
                mean=sensor.stats.mean,
            )
            body.add_namespace("senhub", LINK_RELATIONS_URL)
            body.add_control("self", api.url_for(SensorStats, sensor=sensor))
            body.add_control("up", api.url_for(SensorItem, sensor=sensor))
            body.add_control_delete_stats(sensor)
            return Response(json.dumps(body), 200, mimetype=MASON)
        else:
            self._send_task(sensor)
            return Response(status=202)
            
    def put(self, sensor):
        if not request.json:
            raise UnsupportedMediaType

        try:
            validate(
                request.json,
                Stats.json_schema(),
                format_checker=draft7_format_checker
            )
        except ValidationError as e:
            print(e)
            raise BadRequest(description=str(e))
            
        stats = Stats()
        stats.deserialize(request.json)
        sensor.stats = stats
        db.session.add(sensor)
        db.session.commit()
        return Response(status=204)
        
    def delete(self, sensor):
        db.session.delete(sensor.stats)
        db.session.commit()
        return Response(status=204)
    
    def _send_task(self, sensor):
        # get sensor measurements, values only
        body = SensorhubBuilder(
            data=[meas.value for meas in sensor.measurements],
            sensor=sensor.name
        )
        body.add_control_modify_stats(sensor)
        
        # form a connection, open channel and declare a queue
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(app.config["RABBITMQ_BROKER_ADDR"])
        )
        channel = connection.channel()
        channel.queue_declare(queue="stats")
        
        # publish message (task) to the default exchange
        channel.basic_publish(
            exchange="",
            routing_key="stats",
            body=json.dumps(body)
        )
        connection.close()


app.url_map.converters["sensor"] = SensorConverter
api.add_resource(SensorCollection, "/api/sensors/")
api.add_resource(SensorItem, "/api/sensors/<sensor:sensor>/")
api.add_resource(MeasurementCollection, "/api/sensors/<sensor:sensor>/measurements/")
api.add_resource(
    MeasurementItem,
    "/api/sensors/<sensor:sensor>/measurements/<int:measurement>/"
)
api.add_resource(SensorStats, "/api/sensors/<sensor:sensor>/stats/")

@app.route("/api/")
def entry():
    body = SensorhubBuilder()
    body.add_namespace("senhub", LINK_RELATIONS_URL)
    body.add_control("senhub:sensors-all", api.url_for(SensorCollection))
    return Response(json.dumps(body), 200, mimetype=MASON)

@app.route(LINK_RELATIONS_URL)
def send_link_relations():
    return "link relations"

@app.route("/profiles/<profile>/")
def send_profile(profile):
    return "you requests {} profile".format(profile)

@app.route("/admin/")
def admin_site():
    return app.send_static_file("html/admin.html")

@click.command("init-db")
@with_appcontext
def init_db_command():
    db.create_all()

@click.command("testgen")
@with_appcontext
def generate_test_data():
    import datetime
    import random
    s = Sensor(
        name="test-sensor-1",
        model="testsensor"
    )
    now = datetime.datetime.now()
    interval = datetime.timedelta(seconds=10)
    for i in range(1000):
        m = Measurement(
            value=round(random.random() * 100, 2),
            time=now
        )
        now += interval
        s.measurements.append(m)
    
    db.session.add(s)
    db.session.commit()

app.cli.add_command(init_db_command)
app.cli.add_command(generate_test_data)
