import flask
import os
import uuid
import smtplib
import base64
import requests
import hashlib
import datetime

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from server import db, jwt

from flask import request, Blueprint, current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)
from utils_flask_sqla.response import json_resp_accept_empty_list

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from gncitizen.utils.mail_check import confirm_user_email, confirm_token
from gncitizen.utils.errors import GeonatureApiError
from gncitizen.utils.env import MEDIA_DIR
from gncitizen.utils.sqlalchemy import json_resp
from gncitizen.core.observations.models import ObservationModel
from gncitizen.utils.jwt import admin_required
from .models import UserModel, RevokedTokenModel

import mailchimp_marketing as MailchimpMarketing
from mailchimp_marketing.api_client import ApiClientError

users_api = Blueprint("users", __name__)


@users_api.route("/registration", methods=["POST"])
@json_resp
def registration():
    """
    User registration
    ---
    tags:
      - Authentication
    summary: Creates a new observation
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        description: JSON parameters
        required: true
        schema:
          required:
            - name
            - surname
            - username
            - email
            - password
          properties:
            name:
              type: string
            surname:
              type: string
            username:
              type: string
              example: user1
            organism:
              type: string
            function:
              type: string
            country:
              type: string
            postal_code:
              type: string
            want_newsletter:
              type: boolean
            is_relay:
              type: boolean
            linked_relay_id:
              type: int
            made_known_relay_id:
              type: int
            category:
              type: string
            want_observation_contact:
              type: boolean
            email:
              type: string
            password:
              type: string
              example: user1
    responses:
      200:
        description: user created
    """
    try:
        request_datas = dict(request.get_json())

        if "HCAPTCHA_SECRET_KEY" in current_app.config and current_app.config["HCAPTCHA_SECRET_KEY"] is not None:
            if not 'captchaToken' in request_datas or request_datas['captchaToken'] is None:
                return ({"message": "Veuillez confirmer que vous êtes un humain."}, 400)

            params = {'response': request_datas['captchaToken'], 'secret': current_app.config["HCAPTCHA_SECRET_KEY"]}
            response = requests.post('https://hcaptcha.com/siteverify', data=params)
            captchaResponse = response.json()

            if not captchaResponse['success']:
                return ({"message": "Captcha non valide."}, 400)

        datas_to_save = {}
        for data in request_datas:
            if hasattr(UserModel, data) and data != "password":
                datas_to_save[data] = request_datas[data]

        # Hashed password
        datas_to_save["password"] = UserModel.generate_hash(request_datas["password"])

        if current_app.config["CONFIRM_EMAIL"]["USE_CONFIRM_EMAIL"] == False:
            datas_to_save["active"] = True

        # Protection against admin creation from API
        datas_to_save["admin"] = False
        datas_to_save["is_relay"] = False
        if "extention" in request_datas and "avatar" in request_datas:
            extention = request_datas["extention"]
            imgdata = base64.b64decode(
                request_datas["avatar"].replace(
                    "data:image/" + extention + ";base64,", ""
                )
            )
            filename = "avatar_" + request_datas["username"] + "." + extention
            datas_to_save["avatar"] = filename
        try:
            newuser = UserModel(**datas_to_save)
        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(e)
            # raise GeonatureApiError(e)
            return ({"message": "La syntaxe de la requête est erronée."}, 400)

        try:
            newuser.save_to_db()
        except IntegrityError as e:
            db.session.rollback()
            # error causality ?
            current_app.logger.critical("IntegrityError: %s", str(e))

            if UserModel.find_by_username(newuser.username):
                return (
                    {
                        "message": """L'utilisateur "{}" existe déjà.""".format(
                            newuser.username
                        )
                    },
                    400,
                )

            elif (
                db.session.query(UserModel)
                .filter(UserModel.email == newuser.email)
                .one()
            ):
                return (
                    {
                        "message": "Un email correspondant est déjà enregistré."
                    },
                    400,
                )
            else:
                raise GeonatureApiError(e)

        mailchimp_api_key = current_app.config.get("MAILCHIMP_API_KEY", None)
        if newuser.want_newsletter and mailchimp_api_key is not None:
            try:
                client = MailchimpMarketing.Client()
                client.set_config({
                    "api_key": mailchimp_api_key,
                    "server": "us12"
                })

                response = client.lists.add_list_member(
                    current_app.config.get("MAILCHIMP_LIST_ID", ""),
                    {"email_address": newuser.email, "status": "subscribed"}
                )
                print(response)
            except ApiClientError as error:
                print("Error: {}".format(error.text))

        access_token = create_access_token(identity=newuser.email)
        refresh_token = create_refresh_token(identity=newuser.email)

        # save user avatar
        if "extention" in request_datas and "avatar" in request_datas:
            handler = open(os.path.join(str(MEDIA_DIR), filename), "wb+")
            handler.write(imgdata)
            handler.close()


        try:
            if current_app.config["CONFIRM_EMAIL"]["USE_CONFIRM_EMAIL"] == False:
                message = """Félicitations, l'utilisateur "{}" a été créé.""".format(
                    newuser.username
                ),
                confirm_user_email(newuser, with_confirm_link=False, language=request_datas.get("language", ""))
            else:
                message = """Félicitations, l'utilisateur "{}" a été créé.  \r\n Vous allez recevoir un email pour activer votre compte """.format(
                    newuser.username
                ),
                confirm_user_email(newuser)
        except Exception as e:
            return {"message mail faild": str(e)}, 500

        response = {
            "message": message,
            "username": newuser.username,
            "active": newuser.active,
            "userAvatar": newuser.avatar,
        }

        if newuser.active:
            response["access_token"] = access_token
            response["refresh_token"] = refresh_token

        # send confirm mail
        return response, 200
    except Exception as e:
        current_app.logger.critical("grab all: %s", str(e))
        return {"message": str(e)}, 500


@users_api.route("/login", methods=["POST"])
@json_resp
def login():
    """
    User login
    ---
    tags:
      - Authentication
    summary: Login
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        description: JSON parameters
        required: true
        schema:
          required:
            - email
            - password
          properties:
            email:
              type: string
            password:
              type: string
    responses:
      200:
        description: user created
    """
    try:
        request_datas = dict(request.get_json())
        email = request_datas["email"]
        password = request_datas["password"]
        try:
            current_user = UserModel.query.filter(
                or_(UserModel.email == email, UserModel.username == email)
            ).one()
        except Exception:
            return (
                {"message": """L'email ou le pseudo "{}" n'est pas enregistré.""".format(email)},
                400,
            )
        if not current_user.active:
            return (
                {"message": "Votre compte n'a pas été activé"},
                400,
            )

        email = current_user.email

        if UserModel.verify_hash(password, current_user.password):
            access_token = create_access_token(identity=email)
            refresh_token = create_refresh_token(identity=email)
            return (
                {
                    "message": """Connecté en tant que "{}".""".format(email),
                    "email": email,
                    "username": current_user.as_secured_dict(True).get("username"),
                    "userAvatar": current_user.as_secured_dict(True).get("avatar"),
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                },
                200,
            )
        else:
            return {"message": """Mauvaises informations d'identification"""}, 400
    except Exception as e:
        return {"message": str(e)}, 400


@users_api.route("/logout", methods=["POST"])
@json_resp
@jwt_required()
def logout():
    """
    User logout
    ---
    tags:
      - Authentication
    summary: Logout
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
      - name: authorization
        in: authorization
        description: JSON parameter
        required: true
        schema:
          required:
            - authorization
          properties:
            authorization:
              type: string
              example: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZGVudGl0eSI6ImZjbG9pdHJlIiwiZnJlc2giOmZhbHNlLCJ0eXBlIjoiYWNjZXNzIiwiZXhwIjoxNTMyMjA4Nzk0LCJqdGkiOiI5YmQ5OGEwNC1lMTYyLTQwNWMtODg4Zi03YzlhMTAwNTE2ODAiLCJuYmYiOjE1MzIyMDc4OTQsImlhdCI6MTUzMjIwNzg5NH0.oZKoybFIt4mIPF6LrC2cKXHP8o32vAEcet0xVjpCptE
    responses:
      200:
        description: user disconnected

    """
    jti = get_jwt()["jti"]
    try:
        revoked_token = RevokedTokenModel(jti=jti)
        revoked_token.add()
        return {"msg": "Successfully logged out"}, 200
    except Exception:
        return {"message": "Something went wrong"}, 500


@users_api.route("/token_refresh", methods=["POST"])
@jwt_required(refresh=True)
@json_resp
def token_refresh():
    """Refresh token
    ---
    tags:
      - Authentication
    summary: Refresh token for logged user
    produces:
      - application/json
    responses:
      200:
        description: list all logged users
    """
    current_user = get_jwt_identity()
    access_token = create_access_token(identity=current_user)
    return {"access_token": access_token}


@users_api.route("/allusers", methods=["GET"])
@json_resp
@jwt_required()
@admin_required
def get_allusers():
    """list all users
    ---
    tags:
      - Authentication
    summary: List all registered users
    produces:
      - application/json
    responses:
      200:
        description: list all users
    """
    # allusers = UserModel.return_all()
    allusers = UserModel.return_all()
    return allusers, 200

@users_api.route("/relays", methods=["GET"])
@json_resp_accept_empty_list
def get_relays():
    """list all relays
    ---
    tags:
      - Relays
    summary: List all relays
    produces:
      - application/json
    responses:
      200:
        description: list all relays
    """
    return UserModel.return_relays(), 200

@users_api.route("/user/<int:id>/info", methods=["GET", "PATCH"])
@json_resp
@jwt_required()
def selected_user(id):
    """get or patch user model (only if admin)
    ---
    tags:
      - Authentication
    produces:
      - application/json
    responses:
      200:
        description: selected user model
    """
    try:
        current_user_email = get_jwt_identity()
        current_user = UserModel.query.filter_by(email=current_user_email).one()
        if current_user.admin:
            user = UserModel.query.filter_by(id_user=id).one()
            return get_or_patch_user(user)
        else:
            return (
                {"message": "Forbidden"},
                403,
            )
    except Exception as e:
        # raise GeonatureApiError(e)
        current_app.logger.error("AUTH ERROR:", str(e))
        return (
            {"message": str(e)},
            400,
        )

@users_api.route("/user/info", methods=["GET", "PATCH"])
@json_resp
@jwt_required()
def logged_user():
    """current user model
    ---
    tags:
      - Authentication
    summary: current registered user
    produces:
      - application/json
    responses:
      200:
        description: current user model
    """
    try:
        current_user = get_jwt_identity()
        user = UserModel.query.filter_by(email=current_user).one()
        return get_or_patch_user(user)
    except Exception as e:
        # raise GeonatureApiError(e)
        current_app.logger.error("AUTH ERROR:", str(e))
        return (
            {"message": str(e)},
            400,
        )


def get_or_patch_user(user):
    try:
        if flask.request.method == "GET":
            # base stats, to enhance as we go
            result = user.as_secured_dict(True)
            result["stats"] = {
                "platform_attendance": db.session.query(
                    func.count(ObservationModel.id_role)
                )
                .filter(ObservationModel.id_role == user.id_user)
                .one()[0]
            }

            return ({"message": "Vos données personelles", "features": result}, 200)

        if flask.request.method == "PATCH":
            is_admin = user.admin or False
            current_app.logger.debug("[logged_user] Update current user personnal data")
            request_data = dict(request.get_json())
            if "extention" in request_data and "avatar" in request_data:
                extention = request_data["extention"]
                imgdata = base64.b64decode(
                    request_data["avatar"].replace(
                        "data:image/" + extention + ";base64,", ""
                    )
                )
                filename = "avatar_" + user.username + "." + extention
                request_data["avatar"] = filename + "?" + datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                avatar_path = os.path.join(str(MEDIA_DIR), str(user.as_secured_dict(True)["avatar"]))
                if os.path.exists(avatar_path):
                    os.remove(avatar_path)
                try:
                    handler = open(os.path.join(str(MEDIA_DIR), str(filename)), "wb+")
                    handler.write(imgdata)
                    handler.close()
                except Exception as e:
                    return (
                        {"message": e},
                        500,
                    )

            for data in request_data:
                if hasattr(UserModel, data) and data not in {
                    "id_user",
                    "username",
                    "admin",
                }:
                    setattr(user, data, request_data[data])
            if "newPassword" in request_data:
                user.password = UserModel.generate_hash(request_data["newPassword"])

            user.admin = is_admin

            mailchimp_api_key = current_app.config.get("MAILCHIMP_API_KEY", None)
            if mailchimp_api_key is not None:
                try:
                    client = MailchimpMarketing.Client()
                    client.set_config({
                        "api_key": mailchimp_api_key,
                        "server": "us12"
                    })

                    if user.want_newsletter:
                        client.lists.add_list_member(
                            current_app.config.get("MAILCHIMP_LIST_ID", ""),
                            {"email_address": user.email, "status": "subscribed"}
                        )
                    else:
                        client.lists.delete_list_member(
                            current_app.config.get("MAILCHIMP_LIST_ID", ""),
                            hashlib.md5(user.email.encode('utf-8')).hexdigest()
                        )

                except ApiClientError as error:
                    print("Mailchimp Error: {}".format(error.text))

            user.update()
            return (
                {
                    "message": "Informations personnelles mises à jour. Merci.",
                    "features": user.as_secured_dict(True),
                },
                200,
            )

    except Exception as e:
        # raise GeonatureApiError(e)
        current_app.logger.error("AUTH ERROR:", str(e))
        return (
            {"message": str(e)},
            400,
        )


@users_api.route("/user/delete", methods=["DELETE"])
@json_resp
@jwt_required()
def delete_user():
    """list all logged users
    ---
    tags:
      - Authentication
    summary: Delete current logged user
    consumes:
      - application/json
    produces:
      - application/json
    responses:
      200:
        description: Delete current logged user
    """
    # Get logged user
    current_app.logger.debug("[delete_user] Delete current user")

    current_user = get_jwt_identity()
    if current_user:
        current_app.logger.debug(
            "[delete_user] current user is {}".format(current_user)
        )
        user = UserModel.query.filter_by(email=current_user)
        # get username
        username = user.one().username
        # delete user
        try:
            db.session.query(UserModel).filter(UserModel.username == username).delete()
            db.session.commit()
            current_app.logger.debug(
                "[delete_user] user {} succesfully deleted".format(username)
            )
        except Exception as e:
            db.session.rollback()
            raise GeonatureApiError(e)
            return {"message": str(e)}, 400

        return (
            {
                "message": """Account "{}" have been successfully deleted""".format(
                    username
                )
            },
            200,
        )


@users_api.route("/user/resetpasswd", methods=["POST"])
@json_resp
def reset_user_password():
    request_datas = dict(request.get_json())
    email = request_datas["email"]
    # username = request_datas["username"]

    try:
        user = UserModel.query.filter_by(email=email).one()
    except Exception:
        return (
            {"message": """L'email "{}" n'est pas enregistré.""".format(email)},
            400,
        )

    passwd = uuid.uuid4().hex[0:6]
    passwd_hash = UserModel.generate_hash(passwd)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = current_app.config["RESET_PASSWD"]["SUBJECT"]
    msg["From"] = current_app.config["RESET_PASSWD"]["FROM"]
    msg["To"] = user.email

    # Record the MIME types of both parts - text/plain and text/html.
    part1 = MIMEText(
        current_app.config["RESET_PASSWD"]["TEXT_TEMPLATE"].format(
            passwd=passwd, app_url=current_app.config["URL_APPLICATION"]
        ),
        "plain",
    )
    part2 = MIMEText(
        current_app.config["RESET_PASSWD"]["HTML_TEMPLATE"].format(
            passwd=passwd, app_url=current_app.config["URL_APPLICATION"]
        ),
        "html",
    )

    # Attach parts into message container.
    # According to RFC 2046, the last part of a multipart message, in this case
    # the HTML message, is best and preferred.
    msg.attach(part1)
    msg.attach(part2)

    try:
        with smtplib.SMTP_SSL(
            current_app.config["MAIL"]["MAIL_HOST"],
            int(current_app.config["MAIL"]["MAIL_PORT"]),
        ) as server:
            server.login(
                str(current_app.config["MAIL"]["MAIL_AUTH_LOGIN"]),
                str(current_app.config["MAIL"]["MAIL_AUTH_PASSWD"]),
            )
            server.sendmail(
                current_app.config["MAIL"]["MAIL_FROM"], user.email, msg.as_string()
            )
            server.quit()
        user.password = passwd_hash
        db.session.commit()
        return (
            {"message": "Check your email, you credentials have been updated."},
            200,
        )
    except Exception as e:
        current_app.logger.warning(
            "reset_password: failled to send new credentials. %s", str(e)
        )
        return (
            {
                "message": """Echec d'envoi des informations de connexion: "{}".""".format(
                    str(e)
                )
            },
            500,
        )


@users_api.route("/user/confirmEmail/<token>", methods=["GET"])
@json_resp
def confirm_email(token):
    try:
        email = confirm_token(token)
    except:
        return (
            {"message": "The confirmation link is invalid or has expired."},
            404,
        )
    user = UserModel.query.filter_by(email=email).first_or_404()
    if user.active:
        return (
            {"message": "Account already confirmed. Please login.", "status": 208},
            208,
        )
    else:
        user.active = True
        user.update()
        db.session.commit()
        return (
            {"message": "You have confirmed your account. Thanks!", "status": 200},
            200,
        )
