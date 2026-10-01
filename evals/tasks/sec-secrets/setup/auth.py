import logging

log = logging.getLogger(__name__)


def login(username, password):
    log.info("login attempt user=%s password=%s", username, password)
    return username == "admin" and password == "s3cret"
