"""Module for handling client (merchant) interactions with Gloebit.

Interactions are handled by Merchant class objects, one object per merchant.

Merchant object initialization requires:
  ClientSecrets: Object holding merchant's client secrets.  Created
    with either the client key and secret (from Gloebit Merchant Tools
    page) or a client secrets JSON file (containing same info and more).
  Redirect URI: URI for callback from Gloebit server with credential
    code following user authorization via Gloebit's authorization URI.

A Merchant object provides the following methods:
  user_authorization_url: Provides URL for redirecting user agent to
    get user's authorization.  After successful authorization, the
    user agent will be redirected to the Redirect URI.
  exchange_for_user_credential: Exchanges code (from query parameters
    attached to Redirect URI) for user credential from Gloebit server.
    The user credential contains the resource access token.
  user_info: Returns dictionary of Gloebit user information.  Requires
    user credential (from authorization steps).  Also, merchant must
    have 'user' in its scope.
  purchase: Performs a Gloebit purchase.  Requires user credential (from
    authorization steps), a product name.  Also,
    merchant must have 'transact' in its scope.

Typical flow for single-merchant service:
  1) Import gloebit module.
  2) Create Clientsecrets object.
  3) Create Merchant object using the ClientSecrets object.
  4) Per-user:
     a) Redirect user agent to Gloebit authorization URL (get URL
        from Merchant object).
     b) When Gloebit redirects user agent to redirect URI, give
        query args to Merchant object to exchange for user credential.
     c) Store user credential.
     d) Use credential to look up user info, make purchases, etc.
"""

### TODO
###   * Replace all response returns with exception raises.
###   * Params passed backed when getting user info, what are they?
###   * Improve XSRF checking when exchanging code for credential.

import httplib2
import json
import uuid
import time

from urlparse import urlparse

from oauth2client import clientsecrets, xsrfutil
from oauth2client.client import OAuth2WebServerFlow

from oauth2client import util

GLOEBIT_SERVER = 'www.gloebit.com'
GLOEBIT_SANDBOX = 'sandbox.gloebit.com'
GLOEBIT_OAUTH2_AUTH_URI = 'https://%s/oauth2/authorize'
GLOEBIT_OAUTH2_TOKEN_URI = 'https://%s/oauth2/access-token'
GLOEBIT_VISIT_URI = 'https://%s/purchase/'
GLOEBIT_USER_URI = 'https://%s/user/'
GLOEBIT_TRANSACT_URI = 'https://%s/transact/'
GLOEBIT_LIST_PRODUCT = 'https://%s/get-user-products/'

class Error(Exception):
    """Base error for this module."""

class CrossSiteError(Error):
    """XSRF state check in authorization failed."""

class BadRequestError(Error):
    """Response error from Gloebit not 200.  Code returned in string."""

class AccessTokenError(Error):
    """Error using access token (revoked or expired), reauthorize."""

class UserInfoError(Error):
    """Error trying to lookup Gloebit user info."""

class TransactError(Error):
    """Base error for Gloebit Transact errors."""

class TransactRequestError(TransactError):
    """HTTP status error for Gloebit transact request."""

class TransactFailureError(TransactError):
    """Gloebit transact request was processed but returned success=False."""

class ClientSecrets(object):
    """Container for OAuth2 client secrets."""

    @util.positional(3)
    def __init__(self, client_id, client_secret,
                 redirect_uri=None, auth_uri=None, token_uri=None,
                 visit_uri=None,
                 _sandbox=False):
        """Create a ClientSecrets.

        Args:
          client_id: string, Merchant's OAuth key for Gloebit account.  Cut
            and paste it from Merchant Tools page into the code using this
            method directly (or put into a secrets JSON file).
          client_secret: string, Merchant's OAuth secret for Gloebit account.
            Cut and paste it along with the key.
          redirect_uri: string, Absolute URL for application to handle
            Gloebit callback with code.
          auth_uri: string, URL for Gloebit authorization method.
          token_uri: string, URL for Gloebit access token method.
          visit_uri: string, URL to use when user visits Gloebit
          _sandbox: Boolean, Set to True to use sandbox testing server.
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.auth_uri = auth_uri
        self.visit_uri = visit_uri
        self.token_uri = token_uri

        if _sandbox:
            self.auth_uri = GLOEBIT_OAUTH2_AUTH_URI % GLOEBIT_SANDBOX
            self.token_uri = GLOEBIT_OAUTH2_TOKEN_URI % GLOEBIT_SANDBOX
            self.visit_uri = GLOEBIT_VISIT_URI % GLOEBIT_SANDBOX
        else:
            if auth_uri is None:
                self.auth_uri = GLOEBIT_OAUTH2_AUTH_URI % GLOEBIT_SERVER
            if token_uri is None:
                self.token_uri = GLOEBIT_OAUTH2_TOKEN_URI % GLOEBIT_SERVER
            if visit_uri is None:
                self.visit_uri = GLOEBIT_VISIT_URI % GLOEBIT_SERVER

    @staticmethod
    @util.positional(1)
    def from_file(filename, cache=None, redirect_uri=None, _sandbox=False):
        """Create a ClientSecrets from a clientsecrets JSON file.

        Very closely resembles oauth2client.client.flow_from_clientsecrets().
        """
        client_type, client_info = clientsecrets.loadfile(filename, cache=cache)
        constructor_kwargs = {
            'redirect_uri': redirect_uri,
            'auth_uri': client_info['auth_uri'],
            'token_uri': client_info['token_uri'],
            '_sandbox': _sandbox,
        }
        return ClientSecrets(client_info['client_id'],
                             client_info['client_secret'],
                             **constructor_kwargs)

    @staticmethod
    @util.positional(0)
    def from_server(_sandbox=False):
        """Create a ClientSecrets via the Gloebit server.

        Not yet implemented.
        """
        pass

class Merchant(object):
    """Handles tasks for Gloebit merchants."""

    @util.positional(2)
    def __init__(self, client_secrets,
                 scope='transact inventory character user',
                 redirect_uri=None, secret_key=None):
        """Create a Merchant that will use the given ClientSecrets.

        Args:
          client_secrets: ClientSecrets, Merchant's Gloebit secrets.
          scope: string, Space-separated set of Gloebit methods to request
            authorization for.
          redirect_uri: string, Absolute URL for application to handle
            Gloebit callback with code.  Overrides the redirect_uri from
            the ClientSecrets.
          secret_key: string, Application's secret key; used for cross-site
            forgery prevention, if provided.

        Returns:
          A Merchant ready for user authorization and Gloebit methods.
        """
        self.client_secrets = client_secrets
        self.client_id = client_secrets.client_id
        self.client_secret = client_secrets.client_secret
        self.auth_uri = client_secrets.auth_uri
        self.visit_uri = client_secrets.visit_uri
        self.token_uri = client_secrets.token_uri
        self.scope = scope

        self.redirect_uri = client_secrets.redirect_uri
        if redirect_uri is not None:
            self.redirect_uri = redirect_uri

        self.secret_key = secret_key

        parsed_auth_uri = urlparse(self.auth_uri)
        hostname = parsed_auth_uri.hostname
        self.user_uri = GLOEBIT_USER_URI % hostname
        self.transact_uri = GLOEBIT_TRANSACT_URI % hostname
        self.flow = None


    def ready_flow (self, redirect_uri):
        """ create oauth2 flow object """
        if redirect_uri is None:
            redirect_uri = self.redirect_uri
        self.flow = OAuth2WebServerFlow(self.client_id,
                                        self.client_secret,
                                        self.scope,
                                        redirect_uri=redirect_uri,
                                        auth_uri=self.auth_uri,
                                        token_uri=self.token_uri,
                                        revoke_uri=None)


    @util.positional(1)
    def user_authorization_url(self, user=None, redirect_uri=None):
        """Get the Gloebit URL to initiate oauth2 authorization.

        Args:
          redirect_uri: string, Mechant server's URL that handles the callback
            from the Gloebit authorization server.  This will override the
            URI provided when creating the Merchant object, but only for the
            current authorization flow.

        Notes:
          1) Currently supports http URLs only.  Thus, a non-web-based
             application's callback URI might not work.
        """
        self.ready_flow (redirect_uri)

        if user and self.secret_key is not None:
            self.flow.params['state'] = \
                xsrfutil.generate_token(self.secret_key, user)

        return self.flow.step1_get_authorize_url()

    @util.positional(2)
    def exchange_for_user_credential(self, query_args, user=None):
        """Exchange params from Gloebit authorization for Gloebit credential.

        Accessing the Gloebit authorization URL results in a redirection (after
        the user authorizes access) to the merchant's redirect URI, with a code
        provided as a query-arg.  This function provides the second step of the
        authorization by exchanging the code for a Gloebit credential.

        Args:
          query_arg: dictionary, Query arguments from redirection request.

        Returns:
          An Oauth2Credentials object for authorizing Gloebit requests.
        """

        # Need better checks here.  If we have a secret key and a user, then
        # we need to expect a state and throw an error if we did not get one.
        #
        if user and 'state' in query_args:
            if not xsrfutil.validate_token(self.secret_key,
                                           query_args['state'],
                                           user):
                raise CrossSiteError

        self.ready_flow (None)

        # The Merchant object will not have a flow if the server is
        # restarted and the oauth2 callback is the first access!
        #
        # XXX figure out how to make gloebit cert work here
        http = httplib2.Http()
        http.disable_ssl_certificate_validation = True
        credential = self.flow.step2_exchange(query_args['code'], http)

        return credential

    @util.positional(2)
    def user_info(self, credential):
        """Use credential to retreive Gloebit user information.

        Args:
          credential: Oauth2Credentials object, Gloebit authorization credential
            acquired from 2-step authorization process (oauth2).

        Returns:
          dictionary containing following key-value pairs:
            id: Gloebit unique identifier for user.
            name: User-selected character name for your merchant app.
            params: I don't know yet...

        Raises:
          UserInfoError if the request returns a status other than 200.
        """
        if "user" not in self.scope:
            return None

        access_token = credential.access_token

        # Should the Server object handle the http request instead of
        # getting the uri from it and handling the request here?
        http = httplib2.Http()
        http.disable_ssl_certificate_validation = True # XXX
        resp, response_json = http.request(
            uri=self.user_uri,
            method='GET',
            headers={'Authorization': 'Bearer ' + access_token}
        )

        response = _success_check(resp, response_json, UserInfoError)

        return { 'id': response.get('id', None),
                 'name': response.get('name', None),
                 'params': response.get('params', None), }

    @util.positional(4)
    def purchase(self, credential, product, username=None):
        """Use credential to buy predefined product at via Gloebit.

        Args:
          credential: Oauth2Credentials object, Gloebit authorization credential
            acquired from 2-step authorization process (oauth2).
          product: string, name of product being purchased.
          username: string, Merchant's ID/name for purchaser.  If not given and
            'id' is in merchant's Gloebit scope, will look up user's name and
            use that in purchase request.

        Raises:
        """
        if not username:
            if 'user' in self.scope.split():
                userinfo = self.user_info(credential)
                username = userinfo['name']
            else:
                username = 'unknown'

        transaction = {
            'version':                     1,
            'id':                          str(uuid.uuid4()),
            'request-created':             int(time.time()),
            'product':                     product,
            'consumer-key':                self.client_id,
            'merchant-user-id':            username
        }

        access_token = credential.access_token

        # Should the Server object handle the http request instead of
        # getting the uri from it and handling the request here?
        http = httplib2.Http()
        http.disable_ssl_certificate_validation = True # XXX
        resp, response_json = http.request(
            uri=self.transact_uri,
            method='POST',
            headers={'Authorization': 'Bearer ' + access_token,
                     'Content-Type': 'application/json'},
            body=json.dumps(transaction),
        )

        _success_check(resp, response_json, TransactFailureError)


def _success_check(resp, response_json, exception):
    """Check response and body for success or failure.

    Any response code other than 200 is considered an error.  Probably
    should change that to any 4xx or 5xx response code being an error.

    If response code is 200, then extract the JSON from the body and
    look for a 'success' field.  If exists and not True, raise an error.

    Args:
      resp: dictionary of response headers(?).
      response_json: JSON from response body

    Returns:

    Raises
    """
    if resp.status != 200:
        raise BadRequestError\
              ("Gloebit returned " + str(resp.status) + " status!")

    response = json.loads(response_json)

    if 'success' in response.keys():
        if response['success'] != True:
            if response['reason'] == 'unknown token2':
                raise AccessTokenError
            else:
                raise exception(response['reason'])

    return response
