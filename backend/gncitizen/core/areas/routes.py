import uuid
import xlwt
import shapely
import io

from .models import AreaModel, SpeciesSiteModel, SpeciesSiteObservationModel, SpeciesStageModel, StagesStepModel, \
    MediaOnSpeciesSiteObservationModel, MediaOnStagesStepsModel, AreasAccessModel

from server import db

from flask import Blueprint, request, current_app, json, make_response
from flask_jwt_extended import jwt_required, get_jwt_identity

from sqlalchemy import func, or_
from sqlalchemy.orm import aliased
from shapely.geometry import asShape, Point
from geoalchemy2.shape import from_shape, to_shape
from geojson import FeatureCollection
from utils_flask_sqla_geo.utilsgeometry import circle_from_point

from gncitizen.core.users.models import UserModel
from gncitizen.core.commons.models import ProgramsModel, MediaModel
from gncitizen.utils.errors import GeonatureApiError
from gncitizen.utils.jwt import get_id_role_if_exists
from gncitizen.utils.media import save_upload_files
from gncitizen.utils.sqlalchemy import get_geojson_feature, json_resp
from gncitizen.utils.taxonomy import get_specie_from_cd_nom, mkTaxonRepository
from gncitizen.utils.geo import get_municipality_id_from_wkb

areas_api = Blueprint("areas", __name__)


def format_entity(data, with_geom=True):
    if with_geom:
        feature = get_geojson_feature(data.geom)
    else:
        feature = {"properties": {}}
    data_dict = data.as_dict(True)
    for k in data_dict:
        if k not in ("geom",):
            feature["properties"][k] = data_dict[k]

    return feature


def prepare_list(data, with_geom=True, maximum_count=0, model_name=None):
    features = []
    for element in data:
        formatted = format_entity(element, with_geom)

        if model_name == 'areas':
            linked_observations_number = (
                SpeciesSiteObservationModel.query
                    .join(SpeciesSiteModel, SpeciesSiteModel.id_species_site == SpeciesSiteObservationModel.id_species_site)
                    .join(AreaModel, AreaModel.id_area == SpeciesSiteModel.id_area)
                    .filter(AreaModel.id_area == element.id_area)
                    .count()
            )
            formatted["properties"]["creator_can_delete"] = (linked_observations_number == 0)
        if model_name == 'species_sites':
            linked_observations_number = (
                SpeciesSiteObservationModel.query
                    .filter_by(id_species_site=element.id_species_site)
                    .count()
            )
            formatted["properties"]["creator_can_delete"] = (linked_observations_number == 0)


        features.append(formatted)
    features_data = FeatureCollection(features)
    features_data["count"] = len(data)
    if maximum_count != 0:
        features_data["maximum_count"] = maximum_count
    return features_data


"""Used attri
butes in observation features"""
obs_keys = (
    "id_species_site_observation",
    "observer",
    "id_program",
    "obs_txt",
    "count",
    "date",
    "timestamp_create",
    "json_data",
)


def generate_observation(id_species_site_observation):
    """generate observation from observation id

      :param id_species_site_observation: Observation unique id
      :type id_species_site_observation: int

      :return features: Observations as a Feature dict
      :rtype features: dict
    """

    # Crée le dictionnaire de l'observation
    observation = (
        db.session.query(
            SpeciesSiteObservationModel, UserModel.username
        )
            .join(SpeciesSiteModel, SpeciesSiteObservationModel.id_species_site == SpeciesSiteModel.id_species_site,
                  full=True)
            .join(UserModel, SpeciesSiteObservationModel.id_role == UserModel.id_user, full=True)
            .filter(SpeciesSiteObservationModel.id_species_site_observation == id_species_site_observation)
    ).one()

    result_dict = observation.SpeciesSiteObservationModel.as_dict(True)
    result_dict["observer"] = {"username": observation.username}

    # Populate "geometry"
    features = []
    feature = get_geojson_feature(observation.SpeciesSiteObservationModel.species_site.geom)
    feature["properties"]["cd_nom"] = observation.SpeciesSiteObservationModel.species_site.cd_nom

    # Populate "properties"
    for k in result_dict:
        if k in obs_keys:
            feature["properties"][k] = result_dict[k]

    photos = (
        db.session.query(MediaModel, SpeciesSiteObservationModel)
            .filter(SpeciesSiteObservationModel.id_species_site_observation == id_species_site_observation)
            .join(
            MediaOnSpeciesSiteObservationModel,
            MediaOnSpeciesSiteObservationModel.id_data_source == SpeciesSiteObservationModel.id_species_site_observation,
        )
            .join(MediaModel, MediaOnSpeciesSiteObservationModel.id_media == MediaModel.id_media)
            .all()
    )
    feature["properties"]["photos"] = [
        {
            "url": "/media/{}".format(p.MediaModel.filename),
            "date": p.SpeciesSiteObservationModel.as_dict()["date"],
            "author": p.SpeciesSiteObservationModel.obs_txt,
        }
        for p in photos
    ]

    taxhub_list_id = (
        ProgramsModel.query.filter_by(
            id_program=observation.SpeciesSiteObservationModel.species_site.area.id_program
        )
            .one()
            .taxonomy_list
    )
    taxon_repository = mkTaxonRepository(taxhub_list_id)
    try:
        taxon = next(
            taxon
            for taxon in taxon_repository
            if taxon and taxon["cd_nom"] == feature["properties"]["cd_nom"]
        )
        feature["properties"]["taxref"] = taxon["taxref"]
        feature["properties"]["medias"] = taxon["medias"]
    except StopIteration:
        pass

    features.append(feature)
    return features


@areas_api.route("/program/<int:pk>/jsonschema", methods=["GET"])
@json_resp
def get_area_jsonschema_by_program(pk):
    try:
        program = ProgramsModel.query.get(pk)
        data_dict = program.area_custom_form.json_schema
        return data_dict, 200
    except Exception as e:
        return {"error_message": str(e)}, 400


@areas_api.route("/<int:pk>/jsonschema", methods=["GET"])
@json_resp
def get_area_jsonschema(pk):
    try:
        area = AreaModel.query.get(pk)
        data_dict = area.program.area_custom_form.json_schema
        return data_dict, 200
    except Exception as e:
        return {"error_message": str(e)}, 400


@areas_api.route("/<int:pk>/species_site/jsonschema", methods=["GET"])
@json_resp
def get_species_site_jsonschema(pk):
    try:
        area = AreaModel.query.get(pk)
        data_dict = area.program.species_site_custom_form.json_schema
        return data_dict, 200
    except Exception as e:
        return {"error_message": str(e)}, 400


@areas_api.route("/species_site/<int:pk>/obs/jsonschema", methods=["GET"])
@json_resp
def get_species_site_obs_jsonschema(pk):
    try:
        species_site = SpeciesSiteModel.query.get(pk)
        data_dict = species_site.area.program.custom_form.json_schema
        return data_dict, 200
    except Exception as e:
        return {"error_message": str(e)}, 400


@areas_api.route("/program/<int:pk>/species_site/jsonschema", methods=["GET"])
@json_resp
def get_species_site_jsonschema_by_program(pk):
    try:
        program = ProgramsModel.query.get(pk)
        data_dict = program.species_site_custom_form.json_schema
        return data_dict, 200
    except Exception as e:
        return {"error_message": str(e)}, 400


@areas_api.route("/current_user", methods=["GET"])
@json_resp
@jwt_required()
def get_user_areas():
    """Get all user's areas
    ---
    tags:
      - Areas (External module)
    definitions:
      FeatureCollection:
        properties:
          type: dict
          description: area properties
        geometry:
          type: geojson
          description: GeoJson geometry
    responses:
      200:
        description: List of all areas
    """
    try:
        user_id = get_id_role_if_exists()
        areas = (AreaModel.query
                 .filter_by(id_role=user_id)
                 .order_by(func.lower(AreaModel.name))
                 .all())

        return prepare_list(areas, model_name="areas")
    except Exception as e:
        return {"error_message": str(e)}, 400


@areas_api.route("/species_sites/current_user", methods=["GET"])
@json_resp
@jwt_required()
def get_user_species_sites():
    """Get all user's species sites
    ---
    tags:
      - Areas (External module)
    definitions:
      FeatureCollection:
        properties:
          type: dict
          description: species site properties
        geometry:
          type: geojson
          description: GeoJson geometry
    responses:
      200:
        description: List of all species sites
    """
    try:
        user_id = get_id_role_if_exists()
        species_sites = (SpeciesSiteModel.query
                         .filter_by(id_role=user_id)
                         .join(AreaModel, AreaModel.id_area == SpeciesSiteModel.id_area)
                         .order_by(func.lower(SpeciesSiteModel.name))
                         .all())
        return prepare_list(species_sites, model_name="species_sites")
    except Exception as e:
        return {"error_message": str(e)}, 400


@areas_api.route("/observations/current_user", methods=["GET"])
@json_resp
@jwt_required()
def get_user_observations():
    """Get all user's observations
    ---
    tags:
      - Areas (External module)
    definitions:
      FeatureCollection:
        properties:
          type: dict
          description: observation properties
    responses:
      200:
        description: List of all observations
    """
    try:
        user_id = get_id_role_if_exists()
        observations = (SpeciesSiteObservationModel.query
                        .join(SpeciesSiteModel,
                              SpeciesSiteObservationModel.id_species_site == SpeciesSiteModel.id_species_site)
                        .join(AreaModel, AreaModel.id_area == SpeciesSiteModel.id_area)
                        .filter(SpeciesSiteObservationModel.id_role == user_id)
                        .order_by(SpeciesSiteObservationModel.timestamp_create.desc())
                        .all()
                        )

        return prepare_list(observations, with_geom=False)
    except Exception as e:
        return {"error_message": str(e)}, 400


@areas_api.route("/admin", methods=["GET"])
@json_resp
@jwt_required()
def get_admin_areas():
    """Get all users' areas
    ---
    tags:
      - Areas (External module)
    definitions:
      FeatureCollection:
        properties:
          type: dict
          description: area properties
        geometry:
          type: geojson
          description: GeoJson geometry
    responses:
      200:
        description: List of all areas
    """
    try:
        current_user_id = get_id_role_if_exists()
        current_user = UserModel.query.get(current_user_id)
        if current_user.admin != 1 and current_user.is_relay != 1:
            return prepare_list([])

        areas_query = AreaModel.query

        if current_user.admin != 1:
            creator = aliased(UserModel)
            relay = aliased(UserModel)
            areas_query = (
                AreaModel.query
                    .join(creator, AreaModel.id_role == creator.id_user)
                    .outerjoin(relay, relay.id_user == creator.linked_relay_id)
                    .filter(or_(relay.id_user == current_user_id, AreaModel.id_role == current_user_id))
            )

        areas = areas_query.order_by(func.lower(AreaModel.name)).all()

        return prepare_list(areas)
    except Exception as e:
        return {"error_message": str(e)}, 400


@areas_api.route("/species_sites/admin", methods=["GET"])
@json_resp
@jwt_required()
def get_admin_species_sites():
    """Get all users' species sites
    ---
    tags:
      - Areas (External module)
    definitions:
      FeatureCollection:
        properties:
          type: dict
          description: species site properties
        geometry:
          type: geojson
          description: GeoJson geometry
    responses:
      200:
        description: List of all species sites
    """
    try:
        current_user_id = get_id_role_if_exists()
        user = UserModel.query.get(current_user_id)
        if user.admin != 1 and user.is_relay != 1:
            return prepare_list([])

        species_sites_query = (
            SpeciesSiteModel.query
                .join(AreaModel, AreaModel.id_area == SpeciesSiteModel.id_area)
        )

        if user.admin != 1:
            creator = aliased(UserModel)
            relay = aliased(UserModel)
            species_sites_query = (
                species_sites_query
                    .join(creator, SpeciesSiteModel.id_role == creator.id_user)
                    .outerjoin(relay, relay.id_user == creator.linked_relay_id)
                    .filter(or_(relay.id_user == current_user_id, creator.id_user == current_user_id))
            )

        species_sites = species_sites_query.order_by(func.lower(SpeciesSiteModel.name)).all()

        return prepare_list(species_sites)
    except Exception as e:
        return {"error_message": str(e)}, 400


@areas_api.route("/observations/admin", methods=["GET"])
@json_resp
@jwt_required()
def get_admin_observations():
    """Get all users' observations
    ---
    tags:
      - Areas (External module)
    definitions:
      FeatureCollection:
        properties:
          type: dict
          description: observation properties
    responses:
      200:
        description: List of all observations
    """
    try:
        if not request.args.get('page'):
            page = 0
        else:
            page = int(request.args.get('page')) - 1

        if not request.args.get('id_program'):
            id_program = 0
        else:
            id_program = int(request.args.get('id_program'))

        if not request.args.get('page-size'):
            page_size = 1000
        else:
            page_size = int(request.args.get('page-size'))

        current_user_id = get_id_role_if_exists()
        user = UserModel.query.get(current_user_id)
        if user.admin != 1 and user.is_relay != 1:
            return prepare_list([])

        observations_query = (SpeciesSiteObservationModel.query
                .join(SpeciesSiteModel, SpeciesSiteModel.id_species_site == SpeciesSiteObservationModel.id_species_site)
        )

        if user.admin != 1:
            creator = aliased(UserModel)
            relay = aliased(UserModel)
            observations_query = (observations_query
                    .join(creator, SpeciesSiteObservationModel.id_role == creator.id_user)
                    .outerjoin(relay, relay.id_user == creator.linked_relay_id)
                    .filter(or_(relay.id_user == current_user_id, creator.id_user == current_user_id))
            )

        if id_program > 0:
            observations_query = (observations_query
                .join(AreaModel, AreaModel.id_area == SpeciesSiteModel.id_area)
                .filter(AreaModel.id_program == id_program)
            )

        observations_count = observations_query.count()

        observations_query = observations_query.order_by(SpeciesSiteObservationModel.timestamp_create.desc())

        if page_size:
            observations_query = observations_query.limit(page_size * 1)
        if page:
            observations_query = observations_query.offset(page * 1 * page_size * 1)

        observations = observations_query.all()

        features = []
        for observation in observations:
            formatted = {"properties": {}}

            obs_dict = observation.as_dict(True)
            for key in obs_dict:
                formatted["properties"][key] = obs_dict[key]

            photos = (
                MediaModel.query
                    .join(MediaOnSpeciesSiteObservationModel,
                          MediaOnSpeciesSiteObservationModel.id_media == MediaModel.id_media)
                    .filter(
                    MediaOnSpeciesSiteObservationModel.id_data_source == observation.id_species_site_observation)
                    .all()
            )

            formatted["properties"]["photos"] = [
                {
                    "url": "/media/{}".format(p.filename),
                    "id_media": p.id_media,
                }
                for p in photos
            ]

            features.append(formatted)

        data = FeatureCollection(features)
        data["count"] = len(data)
        data["maximum_count"] = observations_count

        return data, 200
    except Exception as e:
        return {"error_message": str(e)}, 400


@areas_api.route("/observers/admin", methods=["GET"])
@json_resp
@jwt_required()
def get_admin_observers():
    """Get all users
    ---
    tags:
      - Areas (External module)
    definitions:
      FeatureCollection:
        properties:
          type: dict
          description: observation properties
    responses:
      200:
        description: List of all observations
    """
    try:
        user_id = get_id_role_if_exists()
        user = UserModel.query.get(user_id)
        if user.admin != 1 and user.is_relay != 1:
            return prepare_list([])

        observers_query = UserModel.query

        if user.admin != 1:
            relay = aliased(UserModel)
            observers_query = (
                observers_query
                    .outerjoin(relay, relay.id_user == UserModel.linked_relay_id)
                    .filter(relay.id_user == user_id)
            )

        observers = observers_query.order_by(UserModel.timestamp_create.desc()).all()

        return prepare_list(observers, with_geom=False)
    except Exception as e:
        return {"error_message": str(e)}, 400


@areas_api.route("/programs/<int:id>", methods=["GET"])
@json_resp
@jwt_required(optional=True)
def get_areas_by_program(id):
    """Get all areas
    ---
    tags:
      - Areas (External module)
    definitions:
      FeatureCollection:
        properties:
          type: dict
          description: area properties
        geometry:
          type: geojson
          description: GeoJson geometry
    responses:
      200:
        description: List of all areas
    """
    try:
        areas_query = AreaModel.query.filter_by(id_program=id)

        program = ProgramsModel.query.get(id)
        if program.is_private:
            user_id = get_id_role_if_exists()
            if user_id:
                areas_query = (areas_query
                               .outerjoin(AreasAccessModel, AreasAccessModel.id_area == AreaModel.id_area)
                               .filter(or_(AreaModel.id_role == user_id, AreasAccessModel.id_user == user_id))
                )
            else:
                return prepare_list([])

        areas = areas_query.order_by(func.lower(AreaModel.name)).all()
        return prepare_list(areas, model_name="areas")
    except Exception as e:
        return {"error_message": str(e)}, 400


@areas_api.route("/program/<int:id>/species_sites/", methods=["GET"])
@json_resp
@jwt_required(optional=True)
def get_species_sites_by_program(id):
    """Get all program's species sites
    ---
    tags:
      - Areas (External module)
    definitions:
      FeatureCollection:
        properties:
          type: dict
          description: species site properties
        geometry:
          type: geojson
          description: GeoJson geometry
    responses:
      200:
        description: List of all species sites
    """
    try:
        species_sites_query = (SpeciesSiteModel.query
                               .join(AreaModel, AreaModel.id_area == SpeciesSiteModel.id_area)
                               .filter_by(id_program=id)
                               )

        program = ProgramsModel.query.get(id)
        if program.is_private:
            user_id = get_id_role_if_exists()
            if user_id:
                species_sites_query = species_sites_query.filter(SpeciesSiteModel.id_role == user_id)
            else:
                return prepare_list([])

        species_sites_query = species_sites_query.order_by(func.lower(SpeciesSiteModel.name))

        species_sites = species_sites_query.all()

        return prepare_list(species_sites, model_name="species_sites")
    except Exception as e:
        return {"error_message": str(e)}, 400


@areas_api.route("/program/<int:id>/observations/", methods=["GET"])
@json_resp
@jwt_required(optional=True)
def get_observations_by_program(id):
    """Get all program's observations
    ---
    tags:
      - Areas (External module)
    definitions:
      FeatureCollection:
        properties:
          type: dict
          description: species site properties
        geometry:
          type: geojson
          description: GeoJson geometry
    responses:
      200:
        description: List of all species sites
    """
    try:
        if not request.args.get('page'):
            page = 0
        else:
            page = int(request.args.get('page')) - 1

        if not request.args.get('page-size'):
            page_size = 1000
        else:
            page_size = int(request.args.get('page-size'))

        observations_query = (SpeciesSiteObservationModel.query
                              .join(SpeciesSiteModel,
                                    SpeciesSiteObservationModel.id_species_site == SpeciesSiteModel.id_species_site)
                              .join(AreaModel, AreaModel.id_area == SpeciesSiteModel.id_area)
                              .filter_by(id_program=id)
                              )

        program = ProgramsModel.query.get(id)
        if program.is_private:
            user_id = get_id_role_if_exists()
            if user_id:
                observations_query = observations_query.filter(SpeciesSiteObservationModel.id_role == user_id)
            else:
                return prepare_list([])

        observations_query = observations_query.order_by(SpeciesSiteObservationModel.timestamp_create.desc())

        observations_count = observations_query.count()

        if page_size:
            observations_query = observations_query.limit(page_size * 1)
        if page:
            observations_query = observations_query.offset(page * 1 * page_size * 1)

        observations = observations_query.all()

        features = []
        for observation in observations:
            formatted = {"properties": {}}

            obs_dict = observation.as_dict(True)
            for key in obs_dict:
                formatted["properties"][key] = obs_dict[key]

            photos = (
                MediaModel.query
                    .join(MediaOnSpeciesSiteObservationModel,
                          MediaOnSpeciesSiteObservationModel.id_media == MediaModel.id_media)
                    .filter(
                    MediaOnSpeciesSiteObservationModel.id_data_source == observation.id_species_site_observation)
                    .all()
            )

            formatted["properties"]["photos"] = [
                {
                    "url": "/media/{}".format(p.filename),
                    "id_media": p.id_media,
                }
                for p in photos
            ]

            features.append(formatted)

        data = FeatureCollection(features)
        data["count"] = len(data)
        data["maximum_count"] = observations_count

        return data, 200

    except Exception as e:
        return {"error_message": str(e)}, 400


@areas_api.route("/<int:pk>", methods=["GET"])
@json_resp
def get_area(pk):
    """Get an area by id
    ---
    tags:
      - Areas (External module)
    parameters:
      - name: pk
        in: path
        type: integer
        required: true
        example: 1
    definitions:
      properties:
        type: dict
        description: area properties
      geometry:
        type: geojson
        description: GeoJson geometry
    responses:
      200:
        description: An area detail
    """
    try:
        area = AreaModel.query.get(pk)
        formatted_area = format_entity(area)
        species_sites = prepare_list(
            SpeciesSiteModel.query.filter_by(id_area=pk)
                .order_by(SpeciesSiteModel.timestamp_update.desc())
                .all()
        )

        for species_site in species_sites['features']:
            last_observation = (SpeciesSiteObservationModel.query
                                .filter_by(id_species_site=species_site['properties']['id_species_site'])
                                .order_by(SpeciesSiteObservationModel.timestamp_create.desc())
                                .first()
            )
            if last_observation is not None:
                species_site["properties"]["last_observation"] = last_observation.as_dict(True)

        formatted_area["properties"]["species_sites"] = species_sites

        return {"features": [formatted_area]}, 200
    except Exception as e:
        return {"error_message": str(e)}, 400


@areas_api.route("/", methods=["POST"])
@json_resp
@jwt_required(optional=True)
def post_area():
    """Ajout d'une zone
    Post an area
        ---
        tags:
          - Areas (External module)
        summary: Creates a new area
        consumes:
          - application/json
        produces:
          - application/json
        parameters:
          - name: body
            in: body
            description: JSON parameters.
            required: true
            schema:
              id: Area
              properties:
                id_program:
                  type: integer
                  description: Program foreign key
                  required: true
                  example: 1
                name:
                  type: string
                  description: Area name
                  default:  none
                  example: "Area 1"
                geometry:
                  type: string
                  example: {"type":"Point", "coordinates":[5,45]}
        responses:
          200:
            description: Area created
        """
    try:
        request_data = dict(request.get_json())

        datas2db = {}
        for field in request_data:
            if hasattr(AreaModel, field):
                datas2db[field] = request_data[field]
        current_app.logger.debug("datas2db: %s", datas2db)
        try:
            new_area = AreaModel(**datas2db)
        except Exception as e:
            current_app.logger.debug(e)
            raise GeonatureApiError(e)

        try:
            json_data = request_data.get("json_data")
            if json_data is not None:
                new_area.json_data = json.loads(json_data)
        except Exception as e:
            current_app.logger.warning("[post_areas] json_data ", e)
            raise GeonatureApiError(e)

        try:
            coordinates = request_data.get("geometry", {}).get("coordinates", [])

            if len(coordinates) == 2:
                latitude = coordinates[1]
                longitude = coordinates[0]
            else:
                message = "[post_areas] invalid coordinates"
                current_app.logger.warning(message)
                raise GeonatureApiError(message)

            p = shapely.geometry.Point(longitude, latitude)

            try:
                new_area.municipality = get_municipality_id_from_wkb(from_shape(p, srid=4326))
            except Exception as e:
                current_app.logger.warning("[post_area] municipality ", e)

            wkt = circle_from_point(p, radius=500, nb_point=100)
            new_area.geom = from_shape(wkt, srid=4326)
        except Exception as e:
            current_app.logger.debug(e)
            raise GeonatureApiError(e)

        id_role = get_id_role_if_exists()
        if id_role is not None:
            new_area.id_role = id_role
            role = UserModel.query.get(id_role)
            new_area.obs_txt = role.username
            new_area.email = role.email
        else:
            if new_area.obs_txt is None or len(new_area.obs_txt) == 0:
                new_area.obs_txt = "Anonyme"

        new_area.uuid_sinp = uuid.uuid4()

        db.session.add(new_area)
        db.session.commit()
        # Réponse en retour
        result = AreaModel.query.get(new_area.id_area)
        return {"message": "New area created.", "features": [format_entity(result)]}, 200
    except Exception as e:
        current_app.logger.warning("Error: %s", str(e))
        return {"error_message": str(e)}, 400


@areas_api.route("/", methods=["PATCH"])
@json_resp
@jwt_required()
def update_area():
    try:
        current_user_email = get_jwt_identity()
        current_user = UserModel.query.filter_by(email=current_user_email).one()

        update_data = dict(request.get_json())
        print(update_data)
        area = AreaModel.query.filter_by(id_area=update_data.get("id_area", 0))
        if current_user.email != UserModel.query.get(area.first().id_role).email and current_user.admin != 1:
            return ("unauthorized"), 403

        update_area = {}
        for prop in ["name"]:
            update_area[prop] = update_data[prop]
        try:
            coordinates = update_data.get("geometry", {}).get("coordinates", [])

            if len(coordinates) == 2:
                latitude = coordinates[1]
                longitude = coordinates[0]
            else:
                message = "[patch_areas] invalid coordinates"
                current_app.logger.warning(message)
                raise GeonatureApiError(message)

            p = shapely.geometry.Point(longitude, latitude)

            try:
                update_area["municipality"] = get_municipality_id_from_wkb(from_shape(p, srid=4326))
            except Exception as e:
                current_app.logger.warning("[update_area] municipality ", e)

            wkt = circle_from_point(p, radius=500, nb_point=100)
            update_area['geom'] = from_shape(wkt, srid=4326)

        except Exception as e:
            current_app.logger.warning("[update_area] coords ", e)
            raise GeonatureApiError(e)

        try:
            json_data = update_data.get("json_data")
            if json_data is not None:
                update_area["json_data"] = json.loads(json_data)
        except Exception as e:
            current_app.logger.warning("[update_area] json_data ", e)
            raise GeonatureApiError(e)

        area.update(update_area, synchronize_session="fetch")
        db.session.commit()
        return ("area updated successfully"), 200
    except Exception as e:
        current_app.logger.critical("[update_area] Error: %s", str(e))
        return {"message": str(e)}, 400


@areas_api.route("/<int:area_id>", methods=["DELETE"])
@json_resp
@jwt_required()
def delete_area(area_id):
    current_user_email = get_jwt_identity()
    current_user = UserModel.query.filter_by(email=current_user_email).one()
    try:
        area = (
            db.session.query(AreaModel, UserModel)
            .filter(AreaModel.id_area == area_id)
            .join(UserModel, AreaModel.id_role == UserModel.id_user, full=True)
            .first()
        )

        linked_observations_number = (
            SpeciesSiteObservationModel.query
                .join(SpeciesSiteModel, SpeciesSiteModel.id_species_site == SpeciesSiteObservationModel.id_species_site)
                .join(AreaModel, AreaModel.id_area == SpeciesSiteModel.id_area)
                .filter(AreaModel.id_area == area_id)
                .count()
        )

        if area and ((current_user.email == area.UserModel.email and linked_observations_number == 0) or current_user.admin):
            AreaModel.query.filter_by(id_area=area_id).delete()
            db.session.commit()
            return ("Area deleted successfully"), 200
        else:
            return ("delete unauthorized"), 403
    except Exception as e:
        return {"message": str(e)}, 500


@areas_api.route("/species_sites/<int:pk>", methods=["GET"])
@json_resp
def get_species_site(pk):
    """Get an species site by id
    ---
    tags:
      - Areas (External module)
    parameters:
      - name: pk
        in: path
        type: integer
        required: true
        example: 1
      - name: with_stages
        in: query
        type: boolean
        description: stages and steps desired (true) or not (false, default)
      - name: with_observations
        in: query
        type: boolean
        description: observations desired (true, default) or not (false)
    definitions:
      properties:
        type: dict
        description: species site properties
      geometry:
        type: geojson
        description: GeoJson geometry
    responses:
      200:
        description: A species site detail
    """
    try:
        species_site = SpeciesSiteModel.query.get(pk)
        formatted_species_site = format_entity(species_site)

        if request.args.get("with_observations") is None or request.args.get("with_observations") != 'false':
            observations = prepare_list(
                SpeciesSiteObservationModel.query.filter_by(id_species_site=pk)
                    .order_by(SpeciesSiteObservationModel.timestamp_update.desc())
                    .all(),
                with_geom=False
            )
            formatted_species_site["properties"]["observations"] = observations

        if request.args.get("with_stages"):
            stages = prepare_list(
                SpeciesStageModel.query.filter_by(cd_nom=species_site.cd_nom)
                    .order_by(SpeciesStageModel.order.asc())
                    .all(),
                with_geom=False
            )
            for stage in stages.features:
                steps = prepare_list(
                    StagesStepModel.query.filter_by(id_species_stage=stage['properties']['id_species_stage'])
                        .order_by(StagesStepModel.order.asc())
                        .all(),
                    with_geom=False
                )

                for step in steps.features:
                    photos = (
                        MediaOnStagesStepsModel.query.filter_by(id_data_source=step['properties']['id_stages_step'])
                            .order_by(MediaOnStagesStepsModel.id_match.asc())
                            .all())

                    step["properties"]["photos"] = [
                        {
                            "url": "/media/{}".format(photo.media.filename),
                        }
                        for photo in photos
                    ]

                stage["properties"]["steps"] = steps

            formatted_species_site["properties"]["stages"] = stages

        return {"features": [formatted_species_site]}, 200
    except Exception as e:
        return {"error_message": str(e)}, 400


@areas_api.route("/species_sites/", methods=["POST"])
@json_resp
@jwt_required(optional=True)
def post_species_site():
    """Ajout d'un site d'individu
    Post a species site
        ---
        tags:
          - Areas (External module)
        summary: Creates a new species site
        consumes:
          - application/json
        produces:
          - application/json
        parameters:
          - name: body
            in: body
            description: JSON parameters.
            required: true
            schema:
              id: Area
              properties:
                id_area:
                  type: integer
                  description: Area foreign key
                  required: true
                  example: 1
                name:
                  type: string
                  description: Species site name
                  default:  none
                  example: "Species site 1"
                geometry:
                  type: string
                  example: {"type":"Point", "coordinates":[5,45]}
        responses:
          200:
            description: Species site created
        """
    try:
        request_data = dict(request.get_json())

        datas2db = {}
        for field in request_data:
            if hasattr(SpeciesSiteModel, field):
                datas2db[field] = request_data[field]
        current_app.logger.debug("datas2db: %s", datas2db)
        try:
            new_species_site = SpeciesSiteModel(**datas2db)
        except Exception as e:
            current_app.logger.debug(e)
            raise GeonatureApiError(e)

        try:
            json_data = request_data.get("json_data")
            if json_data is not None:
                new_species_site.json_data = json.loads(json_data)
        except Exception as e:
            current_app.logger.warning("[post_species_site] json_data ", e)
            raise GeonatureApiError(e)

        try:
            shape = asShape(request_data["geometry"])
            new_species_site.geom = from_shape(Point(shape), srid=4326)
        except Exception as e:
            current_app.logger.debug(e)
            raise GeonatureApiError(e)

        id_role = get_id_role_if_exists()
        if id_role is not None:
            new_species_site.id_role = id_role
            role = UserModel.query.get(id_role)
            new_species_site.obs_txt = role.username
            new_species_site.email = role.email
        else:
            if new_species_site.obs_txt is None or len(new_species_site.obs_txt) == 0:
                new_species_site.obs_txt = "Anonyme"

        new_species_site.uuid_sinp = uuid.uuid4()

        db.session.add(new_species_site)
        db.session.commit()
        # Réponse en retour
        result = SpeciesSiteModel.query.get(new_species_site.id_species_site)
        return {"message": "New species site created.", "features": [format_entity(result)]}, 200
    except Exception as e:
        current_app.logger.warning("Error: %s", str(e))
        return {"error_message": str(e)}, 400


@areas_api.route("/species_sites/", methods=["PATCH"])
@json_resp
@jwt_required()
def update_species_site():
    try:
        current_user_email = get_jwt_identity()
        current_user = UserModel.query.filter_by(email=current_user_email).one()

        update_data = dict(request.get_json())
        species_site = SpeciesSiteModel.query.filter_by(id_species_site=update_data.get("id_species_site"))
        if current_user.email != UserModel.query.get(species_site.first().id_role).email and current_user.admin != 1:
            return ("unauthorized"), 403

        update_species_site = {}
        for prop in ["name"]:
            update_species_site[prop] = update_data[prop]

        try:
            _coordinates = update_data["geometry"]["coordinates"]
            _point = Point(_coordinates[0], _coordinates[1])
            _shape = asShape(_point)
            update_species_site["geom"] = from_shape(Point(_shape), srid=4326)
        except Exception as e:
            current_app.logger.warning("[update_species_site] coords ", e)
            raise GeonatureApiError(e)

        try:
            json_data = update_data.get("json_data")
            if json_data is not None:
                update_species_site["json_data"] = json.loads(json_data)
                print(update_species_site["json_data"])
        except Exception as e:
            current_app.logger.warning("[update_observation] json_data ", e)
            raise GeonatureApiError(e)

        species_site.update(update_species_site, synchronize_session="fetch")
        db.session.commit()
        return ("species_site updated successfully"), 200
    except Exception as e:
        current_app.logger.critical("[update_species_site] Error: %s", str(e))
        return {"message": str(e)}, 400


@areas_api.route("/species_sites/<int:species_site_id>", methods=["DELETE"])
@json_resp
@jwt_required()
def delete_species_site(species_site_id):
    current_user_email = get_jwt_identity()
    current_user = UserModel.query.filter_by(email=current_user_email).one()
    try:
        species_site = (
            db.session.query(SpeciesSiteModel, UserModel)
            .filter(SpeciesSiteModel.id_species_site == species_site_id)
            .join(UserModel, SpeciesSiteModel.id_role == UserModel.id_user, full=True)
            .first()
        )

        linked_observations_number = (
            SpeciesSiteObservationModel.query
                .filter_by(id_species_site=species_site_id)
                .count()
        )

        if species_site and ((current_user.email == species_site.UserModel.email and linked_observations_number == 0) or current_user.admin):
            SpeciesSiteModel.query.filter_by(id_species_site=species_site_id).delete()
            db.session.commit()
            return ("species_site deleted successfully"), 200
        else:
            return ("delete unauthorized "+species_site.name), 403
    except Exception as e:
        return {"message": str(e)}, 500


@areas_api.route("/species_sites/<int:species_site_id>/observations", methods=["POST"])
@json_resp
@jwt_required(optional=True)
def post_observation(species_site_id):
    try:
        request_data = request.form

        new_observation = SpeciesSiteObservationModel(
            id_species_site=species_site_id, date=request_data.get("date", None), id_stages_step=request_data.get("stages_step_id", None),
        )

        try:
            json_data = request_data.get("json_data")
            if json_data is not None:
                new_observation.json_data = json.loads(json_data)
        except Exception as e:
            current_app.logger.warning("[post_areas] json_data ", e)
            raise GeonatureApiError(e)


        id_role = get_id_role_if_exists()
        if id_role is not None:
            new_observation.id_role = id_role
            role = UserModel.query.get(id_role)
            new_observation.obs_txt = role.username
            new_observation.email = role.email
        else:
            if new_observation.obs_txt is None or len(new_observation.obs_txt) == 0:
                new_observation.obs_txt = "Anonyme"

        new_observation.uuid_sinp = uuid.uuid4()

        db.session.add(new_observation)
        db.session.commit()

        result = SpeciesSiteObservationModel.query.get(new_observation.id_species_site_observation)
        response_dict = result.as_dict()

        # Enregistrement de la photo et correspondance Obs Photo
        try:
            files = request.files
            if request_data.get("photos[0]", None) is not None:
                max_length = len(request_data.keys())
                files = []
                for index in range(max_length):
                    if request_data.get("photos[" + str(index) + "]", None) is None:
                        break
                    files.append(request_data.get("photos[" + str(index) + "]"))

            file = save_upload_files(
                files,
                "species_site_obs",
                result.species_site.cd_nom,
                result.id_species_site_observation,
                MediaOnSpeciesSiteObservationModel,
            )
            current_app.logger.debug(
                "[post_observation] ObsTax UPLOAD FILE {}".format(file)
            )
            response_dict["photos"] = file

        except Exception as e:
            current_app.logger.warning(
                "[post_observation] ObsTax ERROR ON FILE SAVING", str(e)
            )

        # Réponse en retour
        response_dict['program_id'] = result.species_site.area.id_program
        return {"message": "New observation created.", "features": [response_dict]}, 200
    except Exception as e:
        current_app.logger.warning("Error: %s", str(e))
        return {"error_message": str(e)}, 400


@areas_api.route("/observations/", methods=["PATCH"])
@json_resp
@jwt_required()
def update_observation():
    try:
        current_user_email = get_jwt_identity()
        current_user = UserModel.query.filter_by(email=current_user_email).one()

        update_data = request.form

        observation = SpeciesSiteObservationModel.query.filter_by(
            id_species_site_observation=update_data.get("id_species_site_observation", 0)
        )
        if current_user.email != UserModel.query.get(observation.first().id_role).email and current_user.admin != 1:
            return ("unauthorized"), 403

        update_observation = {}
        update_observation["date"] = update_data.get("date", None)
        update_observation["id_stages_step"] = update_data.get("stages_step_id", None)
        update_observation["state"] = update_data.get("state", None)

        try:
            json_data = update_data.get("json_data", None)
            if json_data is not None:
                update_observation["json_data"] = json.loads(json_data)
                print(update_observation["json_data"])
        except Exception as e:
            current_app.logger.warning("[update_observation] json_data ", e)
            raise GeonatureApiError(e)

        observation.update(update_observation, synchronize_session="fetch")

        try:
            # Delete selected existing media
            id_media_to_delete = json.loads(update_data.get("delete_media"), [])
            if len(id_media_to_delete):
                db.session.query(MediaOnSpeciesSiteObservationModel).filter(
                    MediaOnSpeciesSiteObservationModel.id_media.in_(tuple(id_media_to_delete)),
                    MediaOnSpeciesSiteObservationModel.id_data_source
                    == update_data.get("id_species_site_observation"),
                ).delete(synchronize_session="fetch")
                db.session.query(MediaModel).filter(
                    MediaModel.id_media.in_(tuple(id_media_to_delete))
                ).delete(synchronize_session="fetch")
        except Exception as e:
            current_app.logger.warning("[update_observation] delete media ", e)
            raise GeonatureApiError(e)

        try:
            files = request.files
            if update_data.get("photos[0]", None) is not None:
                max_length = len(update_data.keys())
                files = []
                for index in range(max_length):
                    if update_data.get("photos[" + str(index) + "]", None) is None:
                        break
                    files.append(update_data.get("photos[" + str(index) + "]"))

            file = save_upload_files(
                files,
                "species_site_obs",
                "0",
                update_data.get("id_species_site_observation", 0),
                MediaOnSpeciesSiteObservationModel,
            )
            current_app.logger.debug(
                "[update_observation] ObsTax UPLOAD FILE {}".format(file)
            )

        except Exception as e:
            current_app.logger.warning(
                "[update_observation] ObsTax ERROR ON FILE SAVING", str(e)
            )
            # raise GeonatureApiError(e)

        db.session.commit()
        return ("observation updated successfully"), 200
    except Exception as e:
        current_app.logger.critical("[update_observation] Error: %s", str(e))
        return {"message": str(e)}, 400


@areas_api.route("/observations/<int:observation_id>", methods=["DELETE"])
@json_resp
@jwt_required()
def delete_observation(observation_id):
    current_user_email = get_jwt_identity()
    current_user = UserModel.query.filter_by(email=current_user_email).one()
    try:
        observation = (
            db.session.query(SpeciesSiteObservationModel, UserModel)
            .filter(SpeciesSiteObservationModel.id_species_site_observation == observation_id)
            .join(UserModel, SpeciesSiteObservationModel.id_role == UserModel.id_user, full=True)
            .first()
        )
        if observation and (current_user.email == observation.UserModel.email or current_user.admin):
            SpeciesSiteObservationModel.query.filter_by(id_species_site_observation=observation_id).delete()
            db.session.commit()
            return ("observation deleted successfully"), 200
        else:
            return ("delete unauthorized"), 403
    except Exception as e:
        return {"message": str(e)}, 500

@areas_api.route("/species_sites/<int:site_id>/observations/<int:visit_id>/photos", methods=["POST"])
@json_resp
@jwt_required(optional=True)
def post_observation_photo(species_site_id, observation_id):
    try:
        current_app.logger.debug("UPLOAD FILE? " + str(request.files))
        if request.files:
            files = save_upload_files(
                request.files, "species_site_id", species_site_id, observation_id, MediaOnSpeciesSiteObservationModel,
            )
            current_app.logger.debug("UPLOAD FILE {}".format(files))
            return files, 200
        return [], 200
    except Exception as e:
        current_app.logger.error("Error: %s", str(e))
        return {"error_message": str(e)}, 400


@areas_api.route("/observations/<int:pk>", methods=["GET"])
@json_resp
def get_observation(pk):
    """Get on observation by id
         ---
         tags:
          - observations
         parameters:
          - name: pk
            in: path
            type: integer
            required: true
            example: 1
         definitions:
           name:
             type: string
         responses:
           200:
             description: A list of all observations
         """
    try:
        features = generate_observation(pk)
        return {"features": features}, 200
    except Exception as e:
        return {"message": str(e)}, 400


@areas_api.route("/export/<int:user_id>", methods=["GET"])
@jwt_required()
def export_areas_xls(user_id):
    current_user_email = get_jwt_identity()

    try:
        current_user = UserModel.query.get(user_id)
        if current_user_email != current_user.email:
            return ("unauthorized"), 403

        filter_by_user = True
        if (
            request.args.get('all-data')
            and request.args.get('all-data') == 'true'
            and (current_user.admin == 1 or current_user.is_relay == 1)
        ):
            filter_by_user = False

        title_style = xlwt.easyxf("font: bold on")
        date_style = xlwt.easyxf(num_format_str="D/M/YY")
        wb = xlwt.Workbook()
        # SITES SHEET
        ws = wb.add_sheet("Zones")

        areas_query = AreaModel.query

        if filter_by_user:
            areas_query = areas_query.filter_by(id_role=user_id)
        elif current_user.admin != 1:
            creator = aliased(UserModel)
            relay = aliased(UserModel)
            areas_query = (
                areas_query
                    .join(creator, AreaModel.id_role == creator.id_user)
                    .outerjoin(relay, relay.id_user == creator.linked_relay_id)
                    .filter(or_(relay.id_user == current_user.id_user, AreaModel.id_role == current_user.id_user))
            )

        areas = (
            areas_query
                .order_by(func.lower(AreaModel.name))
                .all()
        )

        fields = (
            {"col_name": "ID", "getter": lambda area: area.id_area},
            {"col_name": "Programme", "getter": lambda area: area.program.title},
            {"col_name": "Créateur", "getter": lambda area: area.obs_txt + ' (' + str(area.id_role) + ')'},
            {"col_name": "Nom", "getter": lambda area: area.name},
            {"col_name": "Coord. x", "getter": lambda area: str(area.coordinates[0])},
            {"col_name": "Coord. y", "getter": lambda area: str(area.coordinates[1])},
            {
                "col_name": "Date création",
                "getter": lambda area: area.timestamp_create,
                "style": date_style,
            },
        )

        json_keys = list(set([key for area in areas for key in area.json_data.keys()]))
        row, col = 0, 0
        for field in fields:
            ws.write(row, col, field["col_name"], title_style)
            col += 1
        for key in json_keys:
            if key == "remark":
                key = "Remarque"
            if key == "altitude":
                key = "Altitude"
            ws.write(row, col, key, title_style)
            col += 1
        row, col = 1, 0

        for area in areas:
            area.coordinates = to_shape(area.geom).centroid.coords[0]
            for col, field in enumerate(fields):
                args = []
                if field.get("style"):
                    args.append(field.get("style"))
                ws.write(row, col, field["getter"](area), *args)
            row += 1

        # SPECIES SITES SHEET
        ws = wb.add_sheet("Individus")

        species_sites_query = SpeciesSiteModel.query

        if filter_by_user:
            species_sites_query = species_sites_query.filter_by(id_role=user_id)
        elif current_user.admin != 1:
            creator = aliased(UserModel)
            relay = aliased(UserModel)
            species_sites_query = (
                species_sites_query
                    .join(creator, SpeciesSiteModel.id_role == creator.id_user)
                    .outerjoin(relay, relay.id_user == creator.linked_relay_id)
                    .filter(or_(relay.id_user == current_user.id_user, SpeciesSiteModel.id_role == current_user.id_user))
            )

        species_sites = (
            species_sites_query
                .order_by(func.lower(SpeciesSiteModel.name))
                .all()
        )

        basic_fields = (
            {"col_name": "ID", "getter": lambda s: s.id_species_site},
            {"col_name": "Observateur", "getter": lambda s: s.obs_txt + ' (' + str(s.id_role) + ')'},
            {"col_name": "Nom", "getter": lambda s: s.name},
            {"col_name": "Zone", "getter": lambda s: s.area.name if s.area else ''},
            {"col_name": "Espèce",
             "getter": lambda s: (s.species.nom_vern + " (" + s.species.nom_complet + ")") if s.species else ''},
        )

        json_keys = list(set([key for species_site in species_sites for key in species_site.json_data.keys()]))
        row, col = 0, 0
        for field in basic_fields:
            ws.write(row, col, field["col_name"], title_style)
            col += 1
        for key in json_keys:
            if key == "remark":
                key = "Remarque"
            if key == "altitude":
                key = "Altitude"
            if key == "circumference":
                key = "Circonférence"
            if key == "state":
                key = "Etat"
            ws.write(row, col, key, title_style)
            col += 1
        row, col = 1, 0

        for species_site in species_sites:
            for field in basic_fields:
                args = []
                if field.get("style"):
                    args.append(field.get("style"))
                ws.write(row, col, field["getter"](species_site), *args)
                col += 1
            for key in json_keys:
                if key == "remark":
                    key = "Remarque"
                ws.write(row, col, species_site.json_data.get(key))
                col += 1
            row += 1
            col = 0

        # OBSERVATIONS SHEET
        ws = wb.add_sheet("Observations")

        observations_query = SpeciesSiteObservationModel.query

        if filter_by_user:
            observations_query = observations_query.filter_by(id_role=user_id)
        elif current_user.admin != 1:
            creator = aliased(UserModel)
            relay = aliased(UserModel)
            observations_query = (
                observations_query
                    .join(creator, SpeciesSiteObservationModel.id_role == creator.id_user)
                    .outerjoin(relay, relay.id_user == creator.linked_relay_id)
                    .filter(or_(
                        relay.id_user == current_user.id_user,
                        SpeciesSiteObservationModel.id_role == current_user.id_user
                    ))
            )

        observations = (
            observations_query
                .order_by(SpeciesSiteObservationModel.timestamp_create.desc())
                .all()
        )

        basic_fields = (
            {"col_name": "ID", "getter": lambda s: s.id_species_site_observation},
            {"col_name": "Date obs", "getter": lambda s: s.date, "style": date_style},
            {"col_name": "Date saisie", "getter": lambda s: s.timestamp_create, "style": date_style},
            {"col_name": "Observateur", "getter": lambda s: s.obs_txt + ' (' + str(s.id_role) + ')'},
            {"col_name": "Zone",
             "getter": lambda s: (s.species_site.area.name if s.species_site.area else '') if s.species_site else ''},
            {"col_name": "Individu", "getter": lambda s: s.species_site.name if s.species_site else ''},
            {"col_name": "Espèce",
             "getter": lambda s: (
                 (s.species_site.species.nom_vern + " (" + s.species_site.species.nom_complet + ")")
                 if s.species_site.species
                 else ''
             ) if s.species_site else ''},
            {"col_name": "Stade", "getter": lambda s: s.stages_step.species_stage.name if s.stages_step and s.stages_step.species_stage else ''},
            {"col_name": "Etape", "getter": lambda s: s.stages_step.name if s.stages_step else ''},
        )
        json_keys = list(set([key for observation in observations for key in observation.json_data.keys()]))
        row, col = 0, 0
        for field in basic_fields:
            ws.write(row, col, field["col_name"], title_style)
            col += 1
        for key in json_keys:
            if key == "remark":
                key = "Impression"
            ws.write(row, col, key, title_style)
            col += 1
        row, col = 1, 0

        for observation in observations:
            for field in basic_fields:
                args = []
                if field.get("style"):
                    args.append(field.get("style"))
                ws.write(row, col, field["getter"](observation), *args)
                col += 1
            for key in json_keys:
                ws.write(row, col, observation.json_data.get(key))
                col += 1
            row += 1
            col = 0

        # OBSERVERS SHEET
        if not filter_by_user:
            ws = wb.add_sheet("Observateurs")

            observers_query = UserModel.query

            if current_user.admin != 1:
                relay = aliased(UserModel)
                observers_query = (
                    observers_query
                        .outerjoin(relay, relay.id_user == UserModel.linked_relay_id)
                        .filter(or_(
                            relay.id_user == current_user.id_user,
                            UserModel.id_user == current_user.id_user
                        ))
                )

            observers = (
                observers_query
                    .order_by(UserModel.timestamp_create.desc())
                    .all()
            )

            basic_fields = [
                {"col_name": "ID", "getter": lambda s: s.id_user},
                {"col_name": "Pseudo", "getter": lambda s: s.username},
                {"col_name": "Email", "getter": lambda s: s.email},
                {"col_name": "Organisme", "getter": lambda s: s.organism},
                {"col_name": "Profession", "getter": lambda s: s.function},
                {"col_name": "Catégorie", "getter": lambda s: s.category},
                {"col_name": "Date d'inscription", "getter": lambda s: s.timestamp_create, "style": date_style},
            ]

            if current_user.admin:
                basic_fields.append({"col_name": "Zones associées", "getter": lambda s: s.areas_access})
                basic_fields.append({"col_name": "Statut", "getter": lambda s: 'Admin' if s.admin else ("Relai" if s.is_relay else "Utilisateur")})
                basic_fields.append({"col_name": "Relai lié", "getter": lambda s: s.linked_relay.organism if s.linked_relay else ""})
                basic_fields.append({"col_name": "Pays", "getter": lambda s: s.country})
                basic_fields.append({"col_name": "Code postal", "getter": lambda s: s.postal_code})
                basic_fields.append({"col_name": "Année de naissance", "getter": lambda s: s.birth_year})
                basic_fields.append({"col_name": "Genre", "getter": lambda s: ('Femme' if (s.gender == 'f') else ('Homme' if (s.gender == 'm') else s.gender))})

            row, col = 0, 0
            for field in basic_fields:
                ws.write(row, col, field["col_name"], title_style)
                col += 1
            row, col = 1, 0

            for observer in observers:
                observer.areas_access = "Créées: "
                created_areas = AreaModel.query.filter(AreaModel.id_role == observer.id_user).all()
                for area in created_areas:
                    observer.areas_access += str(area.id_area) + ", "

                observer.areas_access += " / Associées: "

                areas_access = AreasAccessModel.query.filter(AreasAccessModel.id_user == observer.id_user).all()
                for area_access in areas_access:
                    observer.areas_access += str(area_access.id_area) + ", "

                for field in basic_fields:
                    args = []
                    if field.get("style"):
                        args.append(field.get("style"))
                    ws.write(row, col, field["getter"](observer), *args)
                    col += 1
                row += 1
                col = 0

        # In memory save and return xls file
        xls_file = io.BytesIO()
        wb.save(xls_file)
        output = make_response(xls_file.getvalue())
        output.headers["Content-Disposition"] = (
                "attachment; filename=" + "export_areas.xls"
        )
        output.headers["Content-type"] = "application/xls"
        return output
    except Exception as e:
        current_app.logger.warning("Error: %s", str(e))
        return {"error_message": str(e)}, 400
