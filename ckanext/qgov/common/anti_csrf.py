# encoding: utf-8
"""Provides a self-contained filter to prevent Cross-Site Request Forgery,
based on the Double Submit Cookie pattern,
www.owasp.org/index.php/Cross-Site_Request_Forgery_(CSRF)_Prevention_Cheat_Sheet#Double_Submit_Cookie

The filter can be enabled simply by invoking 'intercept_csrf()'.
"""
import hashlib
import hmac
import random
import re
from re import IGNORECASE, MULTILINE
import time
import urllib
from logging import getLogger
import urlparse
import six

from ckan.common import config, request, response as pylons_response, g
from ckan.lib import base
import request_helpers

LOG = getLogger(__name__)

RAW_BEFORE = base.BaseController.__before__

""" Used as the cookie name and input field name.
"""
TOKEN_FIELD_NAME = 'token'

"""
This will match a POST form that has whitespace after the opening tag (which all existing forms do).
Once we have injected a token immediately after the opening tag,
it won't match any more, which avoids redundant injection.
"""
POST_FORM = re.compile(r'(<form [^>]*method=["\']post["\'][^>]*>)(\s[^<]*<)',
                       IGNORECASE | MULTILINE)

"""The format of the token HTML field.
"""
TOKEN_VALIDATION_PATTERN = re.compile(r'^[0-9a-z]+![0-9]+/[0-9]+/[-_a-z0-9%]+$',
                                      IGNORECASE)
API_URL = re.compile(r'^/api\b.*')
CONFIRM_MODULE_PATTERN = r'data-module=["\']confirm-action["\']'
HREF_URL_PATTERN = r'href=["\']([^"\']+)'

# We need to edit confirm-action links, which get intercepted by JavaScript,
# regardless of which order their 'data-module' and 'href' attributes appear.
CONFIRM_LINK = re.compile(r'(<a [^>]*{}[^>]*{})(["\'])'.format(
    CONFIRM_MODULE_PATTERN, HREF_URL_PATTERN),
    IGNORECASE | MULTILINE)
CONFIRM_LINK_REVERSED = re.compile(r'(<a [^>]*{})(["\'][^>]*{})'.format(
    HREF_URL_PATTERN, CONFIRM_MODULE_PATTERN),
    IGNORECASE | MULTILINE)


def is_logged_in():
    """ Determine whether the user is currently logged in and thus needs a token.
    TODO Also require a token on login/logout forms.
    """
    return _get_user()


def apply_token(html):
    """ Rewrite HTML to insert tokens if applicable.
    """
    if not is_logged_in() or (
            not POST_FORM.search(html) and not re.search(CONFIRM_MODULE_PATTERN, html)):
        return html

    token = _get_response_token()

    def insert_form_token(form_match):
        """ Inject a token into a POST form. """
        return form_match.group(1) + '<input type="hidden" name="{}" value="{}"/>'.format(TOKEN_FIELD_NAME, token) + form_match.group(2)

    def insert_link_token(link_match):
        """ Inject a token into a link that uses data-module="confirm-action".
        These links are picked up by JavaScript and converted into empty POST requests.
        """
        if TOKEN_FIELD_NAME + '=' in link_match.group(1):
            return link_match.group(0)
        if '?' in link_match.group(2):
            separator = '&'
        else:
            separator = '?'
        return link_match.group(1) + separator + TOKEN_FIELD_NAME + '=' + token + link_match.group(3)

    return CONFIRM_LINK_REVERSED.sub(insert_link_token, CONFIRM_LINK.sub(insert_link_token, POST_FORM.sub(insert_form_token, html)))


def _get_cookie_token():
    """ Retrieve the token expected by the server.

    This will be retrieved from the token cookie, if it exists.
    If not, an error will occur.
    """
    token = None
    if TOKEN_FIELD_NAME in request.cookies:
        LOG.debug("Obtaining token from cookie")
        token = request.cookies.get(TOKEN_FIELD_NAME)
    if token is None or token.strip() == "":
        csrf_fail("CSRF token is blank")

    return token


def _get_user():
    """ Retrieve the current user object.
    """
    return g.userobj


def _get_safe_username():
    """ Retrieve the current username with unsafe characters URL-encoded.
    """
    return urllib.quote(_get_user().name, safe='')


def validate_token(token):
    """ Verify the integrity of the provided token.
    It must have the expected format (hash!timestamp/nonce/username),
    the hash must match the other values,
    the username must match the current account,
    and it must not be older than our limit (currently 30 minutes).
    """
    token_values = read_token_values(token)
    if 'hash' not in token_values:
        return False

    expected_hmac = six.ensure_text(get_digest(token_values['message']))
    if not hmac.compare_digest(expected_hmac, six.ensure_text(token_values['hash'])):
        return False

    now = int(time.time())
    timestamp = token_values['timestamp']
    # allow tokens up to 30 minutes old
    if now < timestamp or now - timestamp > 60 * 30:
        return False

    return token_values['username'] == _get_safe_username()


def read_token_values(token):
    """ Parse the provided token string. Invalid tokens are parsed as empty dicts.
    """
    if not TOKEN_VALIDATION_PATTERN.match(token):
        return {}

    parts = token.split('!', 1)
    message = parts[1]
    # limiting to 2 means that even if a username contains a slash, it won't cause an extra split
    message_parts = message.split('/', 2)

    return {
        "message": message,
        "hash": parts[0],
        "timestamp": int(message_parts[0]),
        "nonce": int(message_parts[1]),
        "username": message_parts[2]
    }


def _get_response_token():
    """Retrieve the token to be injected into pages.

    This will be retrieved from the token cookie, if it exists and is valid.
    If not, a new token will be generated and a new cookie set.
    """
    # ensure that the same token is used when a page is assembled from pieces
    if 'response_token' in request_helpers.scoped_attrs():
        LOG.debug("Reusing response token from request attributes")
        token = request_helpers.scoped_attrs()['response_token']
    elif TOKEN_FIELD_NAME in request.cookies:
        LOG.debug("Obtaining token from cookie")
        token = request.cookies.get(TOKEN_FIELD_NAME)
        if not validate_token(token) or is_soft_expired(token):
            LOG.debug("Invalid or expired cookie token; making new token cookie")
            token = create_response_token()
            request_helpers.scoped_attrs()['created_token'] = True
        request_helpers.scoped_attrs()['response_token'] = token
    else:
        LOG.debug("No valid token found; making new token cookie")
        token = create_response_token()
        request_helpers.scoped_attrs()['created_token'] = True
        request_helpers.scoped_attrs()['response_token'] = token

    return token


def is_soft_expired(token):
    """Check whether the token is old enough to need rotation.
    It may still be valid, but it's time to generate a new one.

    The current rotation age is 10 minutes.
    """
    if not validate_token(token):
        return False

    now = int(time.time())
    token_values = read_token_values(token)

    return now - token_values['timestamp'] > 60 * 10


def _get_secret_key():
    """ Retrieve the secret key to use in generating secure hashes.
    Currently this is the Beaker session secret.
    """
    return config.get('beaker.session.secret')


def get_digest(message):
    """ Generate a secure (unforgeable) hash of the provided data.
    """
    return hmac.HMAC(_get_secret_key(), message, hashlib.sha512).hexdigest()


def create_response_token():
    """ Generate an unforgeable CSRF token. The format of this token is:
    hash!timestamp/nonce/username
    where the hash is a secure HMAC of the other values plus a secret key.
    """
    username = _get_safe_username()
    timestamp = int(time.time())
    nonce = random.randint(1, 999999)
    message = "{}/{}/{}".format(timestamp, nonce, username)
    token = "{}!{}".format(get_digest(message), message)

    # pre-emptively set the token cookie if using Pylons,
    # otherwise assume the after_app_request hook will do it
    if 'set_cookie' in dir(pylons_response):
        set_response_token_cookie(token, pylons_response)
    return token


def set_response_token_cookie(token, response):
    """ Add a generated token cookie to the HTTP response.
    """
    site_url = urlparse.urlparse(config.get('ckan.site_url', ''))
    if site_url.scheme == 'https':
        LOG.debug("Securing CSRF token cookie for site %s", site_url)
        secure_cookies = True
    else:
        LOG.warn("Site %s is not secure! CSRF token may be exposed!", site_url)
        secure_cookies = False
    response.set_cookie(TOKEN_FIELD_NAME, token, secure=secure_cookies, httponly=True)


def is_request_exempt():
    """ Determine whether a request needs to provide a token.
    HTTP methods without side effects (GET, HEAD, OPTIONS) are exempt,
    as are API calls (which should instead provide an API key).
    """
    return not is_logged_in()\
        or API_URL.match(request.path)\
        or request.method in {'GET', 'HEAD', 'OPTIONS'}


def check_csrf():
    """ Check whether the request passes (or is exempt from) CSRF checks.
    """
    return is_request_exempt()\
        or _get_cookie_token() == _get_post_token()


def anti_csrf_before(obj, action, **params):
    """ Wrap the core pre-rendering function to require tokens on applicable requests.
    """
    RAW_BEFORE(obj, action)

    if not check_csrf():
        csrf_fail("Could not match session token with form token")


def csrf_fail(message):
    """ Abort the request and return an error when there is a problem with the CSRF token.
    """
    LOG.error(message)
    base.abort(403, "Your form submission could not be validated")


def _get_post_token():
    """Retrieve the token provided by the client.

    This is normally a single 'token' parameter in the POST body.
    However, for compatibility with 'confirm-action' links,
    it is also acceptable to provide the token as a query string parameter.
    """
    if TOKEN_FIELD_NAME in request_helpers.scoped_attrs():
        return request_helpers.scoped_attrs()[TOKEN_FIELD_NAME]

    post_tokens = request_helpers.get_post_params(TOKEN_FIELD_NAME)

    if post_tokens:
        if len(post_tokens) > 1:
            csrf_fail("More than one CSRF token in form submission")
        else:
            token = post_tokens[0]
    else:
        get_tokens = request_helpers.get_query_params(TOKEN_FIELD_NAME)
        if len(get_tokens) == 1:
            # handle query string token if there are no POST parameters
            # this is needed for the 'confirm-action' JavaScript module
            token = get_tokens[0]
        else:
            csrf_fail("Missing CSRF token in form submission")

    if not validate_token(token):
        csrf_fail("Invalid token format")

    request_helpers.scoped_attrs()[TOKEN_FIELD_NAME] = token
    request_helpers.delete_param(TOKEN_FIELD_NAME)
    return token


def intercept_csrf():
    """ Monkey-patch the core rendering methods to apply our CSRF tokens.
    """
    def _compose_renderer(raw_function):
        def _anti_csrf_function(*args, **kwargs):
            return apply_token(raw_function(*args, **kwargs))
        return _anti_csrf_function

    base.render_jinja2 = _compose_renderer(base.render_jinja2)
    base.flask_render_template = _compose_renderer(base.render_jinja2)
    base.BaseController.__before__ = anti_csrf_before
