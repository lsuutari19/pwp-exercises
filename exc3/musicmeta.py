import datetime
import json
import time
import click
from flask import Flask, Response, request, redirect, send_from_directory, url_for
from flask.cli import with_appcontext
from flask_sqlalchemy import SQLAlchemy
from flask_restful import Resource, Api
from jsonschema import validate, ValidationError, draft7_format_checker
from sqlalchemy.engine import Engine
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError, OperationalError
from flasgger import Swagger
from werkzeug.routing import BaseConverter

app = Flask(__name__, static_folder="static")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///development.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SWAGGER"] = {
    "title": "Sensorhub API",
    "openapi": "3.0.3",
    "uiversion": 3,
    "doc_dir": "./doc",
}
api = Api(app)
db = SQLAlchemy(app)
swagger = Swagger(app, template_file="doc/base.yml")

MASON = "application/vnd.mason+json"
ERROR_PROFILE = "/profiles/error-profile/"
LINK_RELATIONS_URL = "/musicmeta/link-relations#"

ALBUM_PROFILE_URL = "/profiles/album/"
ARTIST_PROFILE_URL = "/profiles/artist/"
TRACK_PROFILE_URL = "/profiles/track/"

LENGTH_LONG = "%H:%M:%S"
LENGTH_SHORT = "%M:%S"

# DATABASE
# |
# v

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

va_artist_table = db.Table("va_artists", 
    db.Column("album_id", db.Integer, db.ForeignKey("album.id"), primary_key=True),
    db.Column("artist_id", db.Integer, db.ForeignKey("artist.id"), primary_key=True)
)


class Track(db.Model):
    
    __table_args__ = (db.UniqueConstraint(
        "disc_number", "track_number", "album_id", name="_track_index_uc"), 
    )
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    disc_number = db.Column(db.Integer, default=1)
    track_number = db.Column(db.Integer, nullable=False)
    length = db.Column(db.Time, nullable=False)
    album_id = db.Column(db.ForeignKey("album.id", ondelete="CASCADE"), nullable=False)
    va_artist_id = db.Column(
        db.ForeignKey("artist.id", ondelete="SET NULL"),
        nullable=True
    )
        
    album = db.relationship("Album", back_populates="tracks")
    va_artist = db.relationship("Artist")

    def __repr__(self):
        return "{} <{}> on {}".format(self.title, self.id, self.album.title)

    def serialize(self, short_form=False):
        if self.va_artist:
            album_artist = "VA"
        else:
            album_artist = self.album.artist.unique_name

        data = MusicMetaBuilder(
            title=self.title,
            disc_number=self.disc_number,
            track_number=self.track_number,
            length=self.length.isoformat(),
        )
        data["artist"] = (self.va_artist and self.va_artist.name) or self.album.artist.name
        data.add_control("profile", href=TRACK_PROFILE_URL)

        if short_form:
            data.add_control("self", href=url_for(
                "track",
                artist=album_artist,
                album=self.album.title,
                disc=self.disc_number,
                track=self.track_number
            ))
            return data

        data.add_namespace("mumeta", LINK_RELATIONS_URL)
        data.add_control("self", href=request.path)
        data.add_control(
            "up", 
            href=url_for("album", artist=album_artist, album=self.album.title)
        )

        if self.va_artist:
            data.add_control(
                "author", 
                href=url_for("artist", artist=self.va_artist.unique_name)
            )
            data.add_control(
                "albums-by", 
                href=url_for("albums_by", artist=self.va_artist.unique_name)
            )
            data.add_control_edit_va_track(self.album, self)
            data.add_control_delete_va_track(self.album, self)
        else:        
            data.add_control(
                "author",
                href=url_for("artist", artist=album_artist)
            )
            data.add_control(
                "albums-by",
                href=url_for("albums_by", artist=album_artist)
            )
            data.add_control_edit_track(
                self.album.artist,
                self.album,
                self
            )
            data.add_control_delete_track(self.album.artist, self.album, self)
        
        return data



    @staticmethod
    def json_schema():
        schema = {
            "type": "object",
            "properties": {},
            "required": ["title", "track_number", "length"]
        }
        props = schema["properties"]
        props["title"] = {
            "description": "Track title",
            "type": "string"
        }
        props["disc_number"] = {
            "description": "Disc number",
            "type": "integer",
            "default": 1
        }
        props["track_number"] = {
            "description": "Track number on disc",
            "type": "integer"
        }
        props["length"] = {
            "description": "Track length",
            "type": "string",
            "format": "duration"
        }
        return schema

class VaTrack:
    #"link to the artist collection, and link to the albums collection"
    @staticmethod
    def json_schema():
        schema = {
            "type": "object",
            "properties": {},
            "required": ["title", "track_number", "length", "va_artist"]
        }
        props = schema["properties"]
        props["title"] = {
            "description": "Track title",
            "type": "string"
        }
        props["disc_number"] = {
            "description": "Disc number",
            "type": "integer",
            "default": 1
        }
        props["track_number"] = {
            "description": "Track number on disc",
            "type": "integer"
        }
        props["length"] = {
            "description": "Track length",
            "type": "string",
            "format": "duration"
        }
        props["va_artist"] = {
            "description": "Track artist unique name (mandatory on VA albums)",
            "type": "string"
        }
        return schema
    
    
class Album(db.Model):
    
    __table_args__ = (db.UniqueConstraint(
        "title", "artist_id", name="_artist_title_uc"), 
    )
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    release = db.Column(db.Date, nullable=False)
    artist_id = db.Column(db.ForeignKey("artist.id", ondelete="CASCADE"), nullable=True)
    genre = db.Column(db.String, nullable=True)
    discs = db.Column(db.Integer, default=1)
    
    artist = db.relationship("Artist", back_populates="albums")
    va_artists = db.relationship("Artist", secondary=va_artist_table)
    tracks = db.relationship(
        "Track",
        cascade="all,delete",
        back_populates="album",
        order_by=(Track.disc_number, Track.track_number)
    )
    
    sortfields = ["artist", "release", "title"]
    
    def __repr__(self):
        return "{} <{}>".format(self.title, self.id)

    def serialize(self, short_form=False):
        data = MusicMetaBuilder(
            title=self.title,
            artist=(self.artist and self.artist.name) or "VA"
        )
        data.add_control("profile", href=ALBUM_PROFILE_URL)
        if short_form:
            data.add_control("self", href=url_for(
                "album", 
                artist=(self.artist and self.artist.unique_name) or "VA",
                album=self.title
            ))
            return data
        
        data.add_namespace("mumeta", LINK_RELATIONS_URL)
        data.add_control("collection", href=url_for("albums"))
        data.update(dict(
            release=self.release.isoformat(),
            genre=self.genre,
            discs=self.discs,
        ))
        if self.artist:
            data.add_control(
                "author", 
                href=url_for("artist", artist=self.artist.unique_name)
            )
            data.add_control(
                "mumeta:albums-by", 
                href=url_for("albums_by", artist=self.artist.unique_name)
            )
            data.add_control_add_track(self.artist, self)
        else:
            data.add_control(
                "mumeta:albums-va",
                href=url_for("albums_va"),
            )
            data.add_control_add_va_track(self)
        
        data.add_control_edit_album(
            self.artist and self.artist.unique_name or "VA",
            self
        )
        data.add_control_delete_album(
            self.artist and self.artist.unique_name or "VA",
            self
        )
        data["items"] = []

        for track in self.tracks:
            data["items"].append(track.serialize(short_form=True))
        
        return data

    @staticmethod
    def json_schema():
        schema = {
            "type": "object",
            "properties": {},
            "required": ["title", "release"]
        }
        props = schema["properties"]
        props["title"] = {
            "description": "Album title",
            "type": "string"
        }
        props["release"] = {
            "description": "Release date",
            "type": "string",
            "format": "date"
        }
        props["genre"] = {
            "description": "Album's genre(s)",
            "type": "string"
        }
        props["discs"] = {
            "description": "Number of discs",
            "type": "integer",
            "default": 1
        }
        return schema
    


class Artist(db.Model):
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    unique_name = db.Column(db.String, nullable=False, unique=True)
    formed = db.Column(db.Date, nullable=True)
    disbanded = db.Column(db.Date, nullable=True)
    location = db.Column(db.String, nullable=False)
    
    albums = db.relationship("Album", cascade="all,delete", back_populates="artist")
    va_albums = db.relationship(
        "Album",
        secondary=va_artist_table,
        back_populates="va_artists",
        order_by=Album.release
    )

    def __repr__(self):
        return "{} <{}>".format(self.name, self.id)

    def serialize(self, short_form=False):
        data = MusicMetaBuilder(
            name=self.name,
            unique_name=self.unique_name,
            formed=self.formed and self.formed.isoformat(),
            disbanded=self.disbanded and self.disbanded.isoformat(),
            location=self.location
        )
        data.add_control("profile", href=ARTIST_PROFILE_URL)
        if short_form:
            data.add_control("self", url_for("artist", artist=self.unique_name))
            return data

        data.add_namespace("mumeta", LINK_RELATIONS_URL)
        data.add_control("self", href=request.path)
        data.add_control("collection", href=url_for("artists"))
        data.add_control_albums_all()
        data.add_control(
            "mumeta:albums-by", 
            href=url_for("albums_by", artist=self.unique_name)
        )
        data.add_control_edit_artist(self)
        data.add_control_delete_artist(self)        
        return data

    @staticmethod
    def json_schema():
        schema = {
            "type": "object",
            "properties": {},
            "required": ["name", "location"]
        }
        props = schema["properties"]
        props["name"] = {
            "description": "Artist name",
            "type": "string"
        }
        props["location"] = {
            "description": "Artist's location",
            "type": "string"
        }
        props["formed"] = {
            "description": "Formed",
            "type": "string",
            "format": "date"
        }
        props["disbanded"] = {
            "description": "Disbanded",
            "type": "string",
            "format": "date"
        }
        return schema
    
# ^
# |
# DATABASE
# UTILITIES
# |
# v


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
            "mumeta:delete",
            href,
            method="DELETE",
            title=title,
        )

class MusicMetaBuilder(MasonBuilder):
    
    def add_control_artists_all(self):
        self.add_control(
            "mumeta:artists-all",
            url_for("artists"),
            title="All artists"
        )
        
    def add_control_albums_all(self):
        self.add_control(
            "mumeta:albums-all",
            url_for("albums") + "?sortby={sortby}",
            title="All albums",
            isHrefTemplate=True,
            schema=self.sort_schema()
        )

    def add_control_add_album(self, artist=None):
        if artist is None:
            href = url_for("albums_va")
            title = "Add a new VA album"
        else:
            href = url_for("albums_by", artist=artist)
            title = "Add a new album for this artist"

        self.add_control_post(
            "mumeta:add-album",
            title,
            href,
            Album.json_schema()
        )

    def add_control_add_artist(self):
        self.add_control_post(
            "mumeta:add-artist",
            "Add a new artist",
            url_for("artists"),
            Artist.json_schema()
        )

    def add_control_add_track(self, artist, album):
        self.add_control_post(
            "mumeta:add-track",
            "Add a track to this album",
            url_for("album", artist=artist.unique_name, album=album.title),
            Track.json_schema()
        )
    
    def add_control_add_va_track(self, album):
        self.add_control_post(
            "mumeta:add-track",
            "Add a track to this album",
            url_for("va_album", album=album.title),
            VaTrack.json_schema()
        )

    def add_control_delete_album(self, artist_name, album):
        self.add_control_delete(
            "Delete this album",
            url_for("album", artist=artist_name, album=album.title),
        )

    def add_control_delete_artist(self, artist):
        self.add_control_delete(
            "Delete this artist",
            url_for("artist", artist=artist.unique_name),
        )

    def add_control_delete_track(self, artist, album, track):
        self.add_control_delete(
            "Delete this track",
            url_for(
                "track",
                artist=artist.unique_name,
                album=album.title,
                disc=track.disc_number,
                track=track.track_number
            ),
        )

    def add_control_delete_va_track(self, album, track):
        self.add_control_delete(
            "Delete this track",
            url_for(
                "va_track",
                album=album.title,
                disc=track.disc_number,
                track=track.track_number
            ),
        )

    def add_control_edit_album(self, artist_name, album):
        self.add_control_put(
            "Edit this album",
            url_for("album", artist=artist_name, album=album.title),
            Album.json_schema()
        )
        
    def add_control_edit_artist(self, artist):
        self.add_control_put(
            "Edit this artist",
            url_for("artist", artist=artist.unique_name),
            Artist.json_schema()
        )

    def add_control_edit_track(self, artist, album, track):
        self.add_control_put(
            "Edit this track",
            url_for(
                "track",
                artist=artist.unique_name,
                album=album.title,
                disc=track.disc_number,
                track=track.track_number
            ), 
            Track.json_schema()
        )
        
    def add_control_edit_va_track(self, album, track):
        self.add_control_put(
            "Edit this track",
            url_for(
                "va_track",
                album=album.title,
                disc=track.disc_number,
                track=track.track_number
            ), 
            VaTrack.json_schema()
        )
    
    @staticmethod
    def sort_schema():
        schema = {
            "type": "object",
            "properties": {},
            "required": []
        }
        props = schema["properties"]
        props["sortby"] = {
            "description": "Field to use for sorting",
            "type": "string",
            "default": "title",
            "enum": ["artist", "title", "genre", "release"]
        }
        return schema

    
def create_error_response(status_code, title, message=None):
    resource_url = request.path
    data = MasonBuilder(resource_url=resource_url)
    data.add_error(title, message)
    data.add_control("profile", href=ERROR_PROFILE)
    return Response(json.dumps(data), status_code, mimetype=MASON)
    
def parse_date(datestring):
    t = time.strptime(datestring, "%Y-%m-%d")
    return datetime.date(t.tm_year, t.tm_mon, t.tm_mday)
    
def parse_time(timestring):
    t = time.strptime(timestring, "%H:%M:%S")
    return datetime.time(t.tm_hour, t.tm_min, t.tm_sec)

# ^
# |
# UTILITIES
# RESOURCES
# |
# v


class AlbumCollection(Resource):

    def get(self, artist=None):
        sortfield = request.args.get("sortby", "title").lower()
        try:
            if artist and artist == "VA":
                collection = Album.query.filter_by(artist=None).order_by(
                    getattr(Album, sortfield)
                )
            elif artist:
                collection = Album.query.join(Artist).filter(
                    Artist.unique_name == artist
                ).order_by(
                    getattr(Album, sortfield)
                )
            elif sortfield == "artist":
                collection = Album.query.join(Artist).order_by(Artist.unique_name)
            else:
                collection = Album.query.order_by(getattr(Album, sortfield))
        except AttributeError as e:
            print(e)
            return create_error_response(400, "Invalid query string", 
                "Accepted values for 'sortby' are: " + 
                ", ".join(Album.sortfields)
            )

        data = MusicMetaBuilder()
        data.add_namespace("mumeta", LINK_RELATIONS_URL)
        data.add_control("self", href=request.path)
        data.add_control_artists_all()
        if artist is not None:
            data.add_control_albums_all()
            if artist == "VA":
                data.add_control_add_album()
            else:
                data.add_control_add_album(artist)
                data.add_control(
                    "author", 
                    url_for("artist", artist=artist)
                )

        data["items"] = []
        for album in collection:
            data["items"].append(album.serialize(short_form=True))
        
        return Response(json.dumps(data), 200, mimetype=MASON)

    def post(self, artist):
        if not request.json:
            return create_error_response(415, "Unsupported media type", "Use JSON")

        try:
            validate(
                request.json,
                Album.json_schema(),
                format_checker=draft7_format_checker
            )
        except ValidationError as e:
            return create_error_response(400, "Invalid JSON document", str(e))

        try:
            album = Album(
                title=request.json["title"],
                release=parse_date(request.json["release"]),
                genre=request.json.get("genre"),
                discs=request.json.get("discs", 1)
            )
        except ValueError:
            return create_error_response(400, "Invalid date format",
                "Release date must be written in ISO format (YYYY-MM-DD)"
            )

        if artist != "VA":
            artist_obj = Artist.query.filter_by(unique_name=artist).first()
            if not artist_obj:
                return create_error_response(404, "Artist not found")
            album.artist = artist_obj
            location = url_for("album", artist=artist_obj.unique_name, album=album.title)
        else:
            location = url_for("va_album", album=album.title)

        try:
            db.session.add(album)
            db.session.commit()
        except IntegrityError:
            return create_error_response(
                409, "Already exists",
                "Artist '{}' already has album with title '{}'".format(
                    artist, album.title
            ))
        except:
            return create_error_response(500, "Database error")

        return Response(status=201, headers={"Location": location})


class AlbumItem(Resource):

    def get(self, album, artist=None):
        if artist is None:
            album = Album.query.filter_by(artist_id=None, title=album).first()
        else:
            album = Album.query.join(Artist).filter(
                Artist.unique_name == artist, Album.title == album
            ).first()
        if not album:
            return create_error_response(404, "Album not found")

        data = album.serialize()
        return Response(json.dumps(data), 200, mimetype=MASON)

    def post(self, album, artist=None):
        if artist is None:
            album = Album.query.filter_by(artist_id=None, title=album).first()
        else:
            album = Album.query.join(Artist).filter(
                Artist.unique_name == artist, Album.title == album
            ).first()

        if not album:
            return create_error_response(404, "Album not found")

        if not request.json:
            return create_error_response(415, "Unsupported media type", "Use JSON")

        try:
            validate(
                request.json,
                Track.json_schema(),
                format_checker=draft7_format_checker,
            )
        except ValidationError as e:
            return create_error_response(400, "Invalid JSON document", str(e))

        track = Track(
            title=request.json["title"],
            track_number=request.json["track_number"],
            disc_number=request.json.get("disc_number", 1),
            length=parse_time(request.json["length"]),
            album=album
        )

        if album.artist is None:
            try:
                va_artist = Artist.query.filter_by(
                    unique_name=request.json["va_artist"]
                ).first()
            except KeyError:
                return create_error_response(
                    400, "Invalid JSON document",
                    "Field 'va_artist' is required for VA albums"
                )

            if va_artist is None:
                return create_error_response(404, "Track artist not found")

            track.va_artist = va_artist
            album.va_artists.append(va_artist)
            album_artist = "VA"
        else:
            album_artist = album.artist.unique_name

        try:
            db.session.add(track)
            db.session.commit()
        except IntegrityError:
            return create_error_response(
                409, "Already exists",
                "Album '{}' already a track at {}.{}".format(
                    album.title, request.json.get("disc_number", 1), request.json["track_number"]
            ))
        except:
            return create_error_response(500, "Database error")

        return Response(
            status=201,
            headers={"Location": url_for(
                "track",
                artist=album_artist,
                album=album.title,
                disc=track.disc_number,
                track=track.track_number
            )}
        )
        
    def put(self, album, artist=None):
        if artist is None:
            album = Album.query.filter_by(artist_id=None, title=album).first()
        else:
            album = Album.query.join(Artist).filter(
                Artist.unique_name == artist, Album.title == album
            ).first()
        
        if not album:
            return create_error_response(404, "Album not found")
        
        if not request.json:
            return create_error_response(415, "Unsupported media type", "Use JSON")
        
        try:
            validate(
                request.json,
                Album.json_schema(),
                format_checker=draft7_format_checker,
            )
        except ValidationError as e:
            return create_error_response(400, "Invalid JSON document", str(e))
        
        album.title = request.json["title"]
        album.genre = request.json.get("genre")
        album.discs = request.json.get("discs", 1)
        try:
            album.release = parse_date(request.json["release"])
        except ValueError:
            return create_error_response(
                400, "Invalid date format",
                "Release date must be written in ISO format (YYYY-MM-DD)"
            )
        
        try:
            db.session.commit()
        except IntegrityError:
            return create_error_response(
                409, "Title reserved",
                "Artist '{}' already has another album with title '{}'".format(
                    artist, album.title
            ))
        except:
            return create_error_response(500, "Database error")
        
        return Response(status=204)

    def delete(self, album, artist=None):
        if artist is None:
            album = Album.query.filter_by(artist_id=None, title=album).first()
        else:
            album = Album.query.join(Artist).filter(
                Artist.unique_name == artist, Album.title == album
            ).first()

        if not album:
            return create_error_response(404, "Album not found")
        
        try:
            db.session.delete(album)
            db.session.commit()
        except KeyboardInterrupt:
            return create_error_response(500, "Database error")
        
        return Response(status=204)


class TrackItem(Resource):

    def _find_instance(self, artist, album, disc, track):
        if artist is None:
            track = Track.query.join(Album).filter(
                Album.artist_id == None,
                Album.title == album,
                Track.disc_number == disc,
                Track.track_number == track
            ).first()
        else:
            track = Track.query.join(Album).join(Artist).filter(
                Artist.unique_name == artist,
                Album.title == album,
                Track.disc_number == disc,
                Track.track_number == track
            ).first()
        return track

    def get(self, album, disc, track, artist=None):
        track = self._find_instance(artist, album, disc, track)
        if not track:
            return create_error_response(404, "Track not found")

        data = track.serialize()
        return Response(json.dumps(data), 200, mimetype=MASON)
    
    def put(self, album, disc, track, artist=None):
        track = self._find_instance(artist, album, disc, track)
        if not track:
            return create_error_response(404, "Track not found")
        
        if not request.json:
            return create_error_response(415, "Unsupported media type", "Use JSON")
        
        try:
            if artist == "VA":
                validate(
                    request.json,
                    VaTrack.json_schema(),
                    format_checker=draft7_format_checker,
                )
            else:
                validate(
                    request.json,
                    Track.json_schema(),
                    format_checker=draft7_format_checker,
                )
        except ValidationError as e:
            return create_error_response(400, "Invalid JSON document", str(e))
        
        track.title = request.json["title"]
        track.disc_number = request.json.get("disc_number", 1)
        track.track_number = request.json["track_number"]
        track.length = datetime.parse_time(request.json["length"])
        
        if track.album.artist is None:
            try:
                va_artist = Artist.query.filter_by(
                    unique_name=request.json["va_artist"]
                ).first()
            except KeyError:
                return create_error_response(
                    400, "Invalid JSON document",
                    "Field 'va_artist' is required for VA albums"
                )
            
            if not va_artist:
                return create_error_response(404, "Track artist not found")
            
            track.va_artist = va_artist
            
        try:
            db.session.commit()
        except IntegrityError:
            return create_error_response(
                409, "Position reserved",
                "Album '{}' already has another track at '{}.{}'".format(
                    album.title,
                    request.json.get("disc_number", 1),
                    request.json["track_number"]
            ))
        except:
            return create_error_response(500, "Database error")
        
        return Response(status=204)
    
    def delete(self, album, disc, track, artist=None):
        track = self._find_instance(artist, album, disc, track)
        if not track:
            return create_error_response(404, "Track not found")

        try:
            db.session.delete(track)
            db.session.commit()
        except:
            return create_error_response(500, "Database error")
        
        return Response(status=204)
    

class ArtistCollection(Resource):

    def get(self):
        artists = Artist.query.order_by(Artist.name)

        data = MusicMetaBuilder()
        data.add_namespace("mumeta", LINK_RELATIONS_URL)
        data.add_control("self", href=request.path)
        data.add_control_albums_all()
        data.add_control_add_artist()
        data["items"] = []

        for artist in artists:
            data["items"].append(artist.serialize(short_form=True))

        return Response(json.dumps(data), 200, mimetype=MASON)

    def post(self):
        if not request.json:
            return create_error_response(415, "Unsupported media type", "Use JSON")
        
        try:
            validate(
                request.json,
                Artist.json_schema(),
                format_checker=draft7_format_checker,
            )
        except ValidationError as e:
            return create_error_response(400, "Invalid JSON document", str(e))

        artist = Artist(
            name=request.json["name"],
            location=request.json["location"]
        )
        
        for key in ["formed", "disbanded"]:
            value = request.json.get(key)
            if value:
                try:
                    setattr(artist, key, parse_date(value))
                except ValueError:
                    return create_error_response(
                        400, "Invalid date format",
                        "Dates must be written in ISO format (YYYY-MM-DD)"
                    )
        
        n = Artist.query.filter(Artist.unique_name.ilike(artist.name.lower())).count()
        if n:
            unique_name = artist.name.lower() + "_f" + str(n)
        else:
            unique_name = artist.name.lower()
        
        artist.unique_name = unique_name

        try:
            db.session.add(artist)
            db.session.commit()
        except:
            return create_error_response(500, "Database error")

        return Response(
            status=201,
            headers={"Location": url_for("artist", artist=unique_name)}
        )


class ArtistItem(Resource):

    def get(self, artist):
        artist = Artist.query.filter_by(unique_name=artist).first()
        if not artist:
            return create_error_response(404, "Artist not found")

        data = artist.serialize()        
        return Response(json.dumps(data), 200, mimetype=MASON)

    def put(self, artist):
        artist = Artist.query.filter_by(unique_name=artist).first()
        if not artist:
            return create_error_response(404, "Artist not found")
        
        if not request.json:
            return create_error_response(415, "Unsupported media type", "Use JSON")
        
        try:
            validate(
                request.json,
                Artist.json_schema(),
                format_checker=draft7_format_checker,
            )
        except ValidationError as e:
            return create_error_response(400, "Invalid JSON document", str(e))
        
        if artist.name != request.json["name"]:
            n = Artist.query.filter(
                Artist.unique_name.ilike(request.json["name"].lower())
            ).count() - 1
            if n:
                unique_name = artist.name.lower() + "_f" + str(n)
            else:
                unique_name = artist.name.lower()
            artist.unique_name = unique_name
            
        artist.name = request.json["name"]
        artist.location = request.json["location"]
        for key in ["formed", "disbanded"]:
            value = request.json.get(key)
            if value:
                try:
                    setattr(artist, key, parse_date(value))
                except ValueError:
                    return create_error_response(
                        400, "Invalid date format",
                        "Dates must be written in ISO format (YYYY-MM-DD)"
                    )
            else:
                setattr(artist, key, None)

        
        try:
            db.session.commit()
        except:
            return create_error_response(500, "Database error")
        
        return Response(status=204)
        
    def delete(self, artist):
        artist = Artist.query.filter_by(unique_name=artist).first()
        if not artist:
            return create_error_response(404, "Artist not found")
        
        try:
            db.session.delete(artist)
            db.session.commit()
        except:
            return create_error_response(500, "Database error")
        
        return Response(status=204)


class AlbumSearch(Resource):

    def get(self):
        try:
            searchterm = request.args["searchterm"]
        except KeyError:
            return create_error_response(
                400, "Missing query parameter",
                "'searchterm' is a mandatory query parameter"
            )
        
        searchfield = request.args.get("searchfield", "title")
        searchmode = request.args.get("searchmode", "equals")
        raise NotImplementedError

# ^
# |
# RESOURCES
# ROUTES
# |
# v


# As the resources serve multiple URIs in this implementation
# multiple endpoints are defined for them. This way Flagger's
# automated API documentation lookup assigns the correct documentation
# for each path.

api.add_resource(
    AlbumCollection, 
    "/api/albums/",
    endpoint="albums",
)
api.add_resource(
    AlbumCollection,
    "/api/artists/VA/albums/",
    endpoint="albums_va",
)
api.add_resource(
    AlbumCollection,
    "/api/artists/<artist>/albums/",
    endpoint="albums_by",
)
api.add_resource(AlbumItem, "/api/artists/VA/albums/<album>/", endpoint="va_album")
api.add_resource(AlbumItem, "/api/artists/<artist>/albums/<album>/", endpoint="album")
api.add_resource(
    TrackItem,
    "/api/artists/VA/albums/<album>/<disc>/<track>/",
    endpoint="va_track"
)
api.add_resource(
    TrackItem,
    "/api/artists/<artist>/albums/<album>/<disc>/<track>/",
    endpoint="track"
)
api.add_resource(ArtistCollection, "/api/artists/", endpoint="artists")
api.add_resource(ArtistItem, "/api/artists/<artist>/", endpoint="artist")
api.add_resource(AlbumSearch, "/api/albums/search/", endpoint="albumsearch")

@app.route("/profiles/<profile_name>")
def redirect_to_profile(profile_name):
    pass

@app.route("/musicmeta/link-relations/")
def send_link_relations_html():
    return "here be link relations"

# ^
# |
# ROUTES
# CLI
# |
# v

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
    Populates the DB with some basic data.
    """
    
    artist_1 = Artist(
        name="Scandal",
        unique_name="scandal",
        location="Osaka, JP",
        formed=datetime.date(2006, 8, 1),
    )
    album_1 = Album(
        title="Hello World",
        release=datetime.date(2014, 12, 3),
        artist=artist_1
    )
    track_1 = Track(
        title="Image",
        track_number=1,
        disc_number=1,
        length=datetime.time(0, 4, 26),
        album=album_1
    )
    track_2 = Track(
        title="Your Song",
        track_number=2,
        disc_number=1,
        length=datetime.time(0, 3, 43),
        album=album_1
    )
    artist_2 = Artist(
        name="Mono",
        unique_name="mono",
        location="Tokyo, JP",
    )
    artist_3 = Artist(
        name="The Ocean",
        unique_name="the ocean",
        location="Berlin, GER",
    )
    album_2 = Album(
        title="Transcendental",
        release=datetime.date(2015, 10, 23)
    )
    track_3 = Track(
        title="Death in Reverse",
        track_number=1,
        disc_number=1,
        length=datetime.time(0, 11, 0),
        va_artist=artist_2,
        album=album_2
    )
    track_4 = Track(
        title="The Quiet Observer",
        track_number=2,
        disc_number=1,
        length=datetime.time(0, 12, 43),
        va_artist=artist_3,
        album=album_2
    )
    db.session.add(artist_1)
    db.session.add(artist_2)
    db.session.add(artist_3)
    db.session.commit()
    
#https://www.semicolonworld.com/question/59482/any-yaml-libraries-in-python-that-support-dumping-of-long-strings-as-block-literals-or-folded-blocks
    
@click.command("update-schemas")
def update_schemas_command():
    import yaml
    
    class literal_unicode(str): pass
    
    def literal_unicode_representer(dumper, data):
        return dumper.represent_scalar(u'tag:yaml.org,2002:str', data, style='|')
    yaml.add_representer(literal_unicode, literal_unicode_representer)

    with open("doc/base.yml") as source:
        doc = yaml.safe_load(source)
    schemas = doc["components"]["schemas"] = {}
    for cls in [Artist, Album, Track, VaTrack]:
        schemas[cls.__name__] = cls.json_schema()

    doc["info"]["description"] = literal_unicode(doc["info"]["description"])
    with open("doc/base.yml", "w") as target:
        target.write(yaml.dump(doc, default_flow_style=False))

app.cli.add_command(init_db_command)
app.cli.add_command(populate_db_command)
app.cli.add_command(update_schemas_command)