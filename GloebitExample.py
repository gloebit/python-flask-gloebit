"""Example module to demonstrate interfacing with Gloebit in a Flask app.
"""

from flask import Flask, request, redirect, session, url_for

from oauth2client.client import OAuth2Credentials

import urllib

### IMPORTANT ###
# This example app stores the user's Gloebit credential in the default
# Flask session.  Never do that in a real app!  Store it someplace secure.

import gloebit

APP = Flask(__name__)

# For the application's secret key, do following commands and replace None
# below with the string.  And then never let anyone know the key.
# >>> import os
# >>> os.urandom(24)
APP.secret_key = None

# Replace test-consumer's credentials with your own.
# Cut-and-paste these from Gloebit Merchant Tools page.  Optionally, you
# can put them in a client secrets JSON file and provide the path to that
# file.
CLIENT_KEY = 'test-consumer'
CLIENT_SECRET = 's3cr3t'

# For single-user simplicity, use a global merchant object.
MERCHANT = gloebit.Merchant(
    gloebit.ClientSecrets(CLIENT_KEY, CLIENT_SECRET, _sandbox=True),
    secret_key=APP.secret_key)

@APP.route('/')
def index():
    """ default page """
    return '''
        <h2>Gloebit Flask Example Portal</h2>
        <a href='%s'>Enter</a>.
    ''' % url_for('login')

@APP.route('/login')
def login():
    """ login page """
    session.pop('username', None)
    redirect_uri = url_for('gloebit_callback', _external=True)
    return redirect(MERCHANT.user_authorization_url(redirect_uri=redirect_uri))

@APP.route('/gloebit_callback')
def gloebit_callback():
    """Exchange code for credential.

    This example stores the credential in the default Flask session.  Do
    not do that in a real system!  Store it someplace secure instead.
    """
    credential = MERCHANT.exchange_for_user_credential(request.args)
    session['credential'] = credential.to_json()

    # Merchant scope includes 'id'.  Grab user's Gloebit username.
    gbinfo = MERCHANT.user_info(credential)
    if gbinfo['name']:
        session['username'] = gbinfo['name']
    else:
        session['username'] = 'Unknown'

    return redirect(url_for('merchant'))

@APP.route('/merchant')
def merchant():
    """ main page """
    if 'msg' in request.args:
        message = request.args['msg']
    else:
        message = "No activity yet"
    return '''
        <h1>Gloebit Flask Example</h1>
        <h2>Welcome, %s.</h2>
        <form action="%s" method="post">
          <input type="hidden" name="size" value="small" />
          <input type="submit" name="visit" value="Visit Gloebit" /><br>
          <input type="submit" name="purchase" value="Purchase small item" />
        </form>
        <p>%s.</p>
        <p><a href="/">Leave</a></p>
        ''' % (session['username'],
               url_for('purchase'),
               message)


@APP.route('/purchase', methods=['POST'])
def purchase():
    """ user submitted form from main page """
    if request.form.get ('visit', False):
        return redirect(MERCHANT.visit_uri +
                        '?return-to=' +
                        urllib.quote(url_for('merchant', _external=True)) +
                        '&r=' + urllib.quote(CLIENT_KEY))

    item = request.form['size'] + " item"
    credential = OAuth2Credentials.from_json(session['credential'])

    try:
        MERCHANT.purchase_product(credential, 'hat')
    except gloebit.AccessTokenError:
        kwargs = {'msg': "Stale token! You need to Leave and Enter again"}
        return redirect(url_for('merchant', **kwargs))
    except gloebit.TransactFailureError as exn:
        kwargs = {'msg': str (exn)}
        return redirect(url_for('merchant', **kwargs))

    return redirect(url_for('merchant', **{'msg': "You bought a " + item}))

if __name__ == "__main__":
    APP.run(debug=True)
