from datetime import datetime, date
from flask import Flask, request, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine
from sqlalchemy import event
from flask_restful import Api, Resource
from werkzeug.exceptions import NotFound, Conflict, BadRequest, UnsupportedMediaType
from werkzeug.routing import BaseConverter
from jsonschema import validate, ValidationError, draft7_format_checker

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///test.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
api = Api(app)
app.app_context().push()

deployments = db.Table("deployments",
                       db.Column("deployment_id", db.Integer, db.ForeignKey(
                           "deployment.id"), primary_key=True),
                       db.Column("sensor_id", db.Integer, db.ForeignKey(
                           "sensor.id"), primary_key=True)
                       )


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    altitude = db.Column(db.Float, nullable=True)
    description = db.Column(db.String(256), nullable=True)

    sensor = db.relationship(
        "Sensor", back_populates="location", uselist=False)

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


class Sensor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), nullable=False, unique=True)
    model = db.Column(db.String(128), nullable=False)
    location_id = db.Column(
        db.Integer, db.ForeignKey("location.id"), unique=True)

    location = db.relationship("Location", back_populates="sensor")
    measurements = db.relationship("Measurement", back_populates="sensor")
    deployments = db.relationship(
        "Deployment", secondary=deployments, back_populates="sensors")

    def serialize(self, short_form=False):
        return {
            "name": self.name,
            "model": self.model,
            "location": self.location and self.location.serialize(short_form=True)
        }

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


class Deployment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start = db.Column(db.DateTime, nullable=True)
    end = db.Column(db.DateTime, nullable=True)
    name = db.Column(db.String(128), nullable=False)

    sensors = db.relationship(
        "Sensor", secondary=deployments, back_populates="deployments")


class Measurement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sensor_id = db.Column(db.Integer, db.ForeignKey(
        "sensor.id", ondelete="SET NULL"))
    value = db.Column(db.Float, nullable=False)
    time = db.Column(db.DateTime, nullable=False)

    sensor = db.relationship("Sensor", back_populates="measurements")

    def deserialize(self, short_form=False):
        return {
            "value": self.value,
            "sensor": self.sensor and self.sensor.serialize(short_form=True),
            "time": date.fromisoformat(self.time)
        }

    @staticmethod
    def json_schema():
        schema = {
            "type": "object",
            "required": ["time", "value"]
        }
        props = schema["properties"] = {}
        props["time"] = {
            "description": "Time of the measurement",
            "type": "string",
            "format": "date-time"
        }
        props["value"] = {
            "description": "Measurement value",
            "type": "number"
        }
        return schema


db.create_all()

"""
    methods start from here
"""


class SensorCollection(Resource):

    def get(self):
        pass

    def post(self):
        if not request.json:
            return "", 415

        try:
            sensor = Sensor(
                name=request.json["name"],
                model=request.json["model"],
            )
            db.session.add(sensor)
            db.session.commit()
        except KeyError:
            return "", 400
        except IntegrityError:
            return "", 409

        return "", 201


class SensorItem(Resource):

    def put(self, sensor):
        if not request.json:
            raise UnsupportedMediaType

        try:
            validate(request.json, Sensor.json_schema())
        except ValidationError as exc:
            raise BadRequest(description=str(exc)) from exc

        sensor.deserialize(request.json)
        try:
            db.session.add(sensor)
            db.session.commit()
        except IntegrityError as exc:
            raise Conflict(
                409,
                f"Sensor with name '{request.json}' already exists."
            ) from exc

        return Response(status=204)


class MeasurementCollection(Resource):
    """
        GET the list of measurements from sensor (not implemented),
        add new measurement POST
    """

    def get(self):
        pass

    def post(self, sensor):
        if not request.json:
            return "", 415

        try:
            validate(request.json, Measurement.json_schema(),
                    format_checker=draft7_format_checker)
        except ValidationError as exc:
            raise BadRequest(description=str(exc)) from exc

        measurement = Measurement(
            sensor_id=sensor.id,
            value=request.json["value"],
            time= datetime.strptime(request.json["time"], '%Y-%m-%dT%H:%M:%S%z')
        )

        print(sensor)
        db.session.add(measurement)
        db.session.commit()
        response = Response(status=201)
        print(api.url_for(MeasurementItem, sensor=sensor.id, measurement=measurement))
        response.headers["Location"] = api.url_for(MeasurementItem, sensor=sensor.name, measurement=measurement.id)
        return response


class MeasurementItem(Resource):
    
    def delete(self, sensor, measurement):
        pass

class SensorConverter(BaseConverter):

    def to_python(self, value):
        db_sensor = Sensor.query.filter_by(name=value).first()
        if db_sensor is None:
            raise NotFound
        return db_sensor

    def to_url(self, value):
        print("SENSOR NAME:", value)
        return str(value)


api.add_resource(SensorCollection, "/api/sensors/")

app.url_map.converters["sensor"] = SensorConverter
app.url_map.converters["measurement"] = SensorConverter
api.add_resource(SensorItem, "/api/sensors/<sensor:sensor>/")
api.add_resource(MeasurementCollection, "/api/sensors/<sensor:sensor>/measurements/")
api.add_resource(MeasurementItem, "/api/sensors/<sensor:sensor>/measurements/<measurement:measurement>/")
#print("Starting SensorHub flask app...\n\n")
#app.run(debug=True)
