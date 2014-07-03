"""Example module to demonstrate interfacing with Gloebit in a Flask app.
"""

from flask import Flask, request, redirect, session, url_for

from oauth2client.client import OAuth2Credentials

from cgi import escape

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
APP.secret_key = \
    '=!\xf0P\xd5\x19\xf6\x11\xc6#\xac\xc9\x1b\x95j\x87\xabd\xbf3\xc0\xc5F\x14'

# Replace test-consumer's credentials with your own.
# Cut-and-paste these from Gloebit Merchant Tools page.  Optionally, you
# can put them in a client secrets JSON file and provide the path to that
# file.
CLIENT_KEY = 'test-consumer'
CLIENT_SECRET = 's3cr3t'

# For single-user simplicity, use a global merchant object.
GLOEBIT = gloebit.Gloebit(
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
    return redirect(GLOEBIT.user_authorization_url(redirect_uri=redirect_uri))

@APP.route('/gloebit_callback')
def gloebit_callback():
    """Exchange code for credential.

    This example stores the credential in the default Flask session.  Do
    not do that in a real system!  Store it someplace secure instead.
    """
    credential = GLOEBIT.exchange_for_user_credential(request.args)
    session['credential'] = credential.to_json()

    # Gloebit scope includes 'name'.  Grab user's Gloebit username.
    gbinfo = GLOEBIT.user_info(credential)
    if gbinfo['name']:
        session['username'] = gbinfo['name']
    else:
        session['username'] = 'Unknown'

    return redirect(url_for('character_select'))


@APP.route('/character-select')
def character_select():
    """ create or select a character """
    if 'msg' in request.args:
        message = request.args['msg']
    else:
        message = ""

    credentials = OAuth2Credentials.from_json(session['credential'])
    characters = GLOEBIT.user_characters (credentials)
    page = '''
    <h1>Gloebit Flask Example</h1>
    <form action="%s" method="post">
    ''' % url_for('character_post')
    for character in characters:
        c_id = escape (character['id'], True)
        c_name = escape (character['name'], True)
        page += '<input type="submit" name="select-%s" value="%s" />' % \
                (c_id, c_name)
        page += '<input type="submit" name="delete-%s" value="delete" /><br>' \
                % (c_id)

    page += '<input type="submit" name="new" value="New Character" />'
    page += '<input type="text" name="new-name">'
    page += '''
    <select name="color">
    <option value="green">Green</option>
    <option value="blue">Blue</option>
    <option value="yellow">Yello</option>
    <option value="red">Red</option>
    </select>
    '''
    page += '<br>'

    page += '</form>'

    page +='''<p>%s</p>
        <p><a href="/">Leave</a></p>
        ''' % (message)

    return page


@APP.route('/character-post', methods=['POST'])
def character_post():
    """ accept a post from the character page """
    credentials = OAuth2Credentials.from_json(session['credential'])
    try:
        if request.form.get ('new', False):
            new_name = request.form.get ('new-name').strip ()
            new_color = request.form.get ('color')
            if new_name == '':
                kwargs = {'msg': "character name can't be blank"}
                return redirect(url_for('character_select', **kwargs))
            character = GLOEBIT.create_character \
                        (credentials, {'name':new_name,
                                       'color':new_color})
            session['character-name'] = character['name']
            session['character-id'] = character['id']
        else:
            characters = GLOEBIT.user_characters (credentials)
            for character in characters:
                if request.form.get ('select-'+character['id'], False):
                    session['character-name'] = character['name']
                    session['character-id'] = character['id']
                if request.form.get ('delete-'+character['id'], False):
                    GLOEBIT.delete_character (credentials, character['id'])
                    return redirect(url_for('character_select'))

    except gloebit.CharacterAccessError, exn:
        kwargs = {'msg': str (exn)}
        return redirect(url_for('character_select', **kwargs))

    return redirect(url_for('main'))


ALL_PRODUCTS = ['hat', 'shirt', 'pants', 'shoe', 'backpack', 'knife', 'torch']



@APP.route('/main')
def main():
    """ main page """
    if 'msg' in request.args:
        message = request.args['msg']
    else:
        message = "No activity yet"


    credential = OAuth2Credentials.from_json(session['credential'])
    user_products = GLOEBIT.user_products (credential)
    character_products = GLOEBIT.character_products \
                         (credential, session['character-id'])

    page = '''
        <h1>Gloebit Flask Example</h1>
        <h2>Welcome, %s (%s).</h2>
        <form action="%s" method="post">
          <input type="submit" name="visit" value="Visit Gloebit" /><br>
        </form>
        ''' % (session['username'],
               session['character-name'],
               url_for('purchase'))

    page += '<h3>User<h3>'
    page += '<form action="%s" method="post">' % url_for('purchase')
    page += '<table>'
    for name in ALL_PRODUCTS:
        page += '''<tr>'''
        page += '''<td>%s</td>''' % (name)
        page += '''<td>%s</td>''' % (user_products.get (name, 0))
        page += '''<td>
        <input type="submit" name="user-grant-%s" value="Grant" /></td>''' % \
        (name)
        page += '''<td>
          <input type="submit" name="user-consume-%s"
                 value="Consume" /></td>''' % \
          (name)
        page += '''<td>
          <input type="submit" name="user-buy-%s" value="Buy" /></td>''' % \
          (name)
        page += '''</tr>'''
    page += '''</table>'''
    page += '</form>'


    page += '<h3>Character<h3>'
    page += '<form action="%s" method="post">' % url_for('purchase')
    page += '<table>'
    for name in ALL_PRODUCTS:
        page += '''<tr>'''
        page += '''<td>%s</td>''' % (name)
        page += '''<td>%s</td>''' % (character_products.get (name, 0))
        page += '''<td>
        <input type="submit" name="character-grant-%s"
               value="Grant" /></td>''' % (name)
        page += '''<td>
          <input type="submit" name="character-consume-%s"
                 value="Consume" /></td>''' % \
          (name)
        page += '''<td>
          <input type="submit" name="character-buy-%s"
                 value="Buy" /></td>''' % \
          (name)
        page += '''</tr>'''
    page += '''</table>'''
    page += '</form>'


    page +='''<p>%s.</p>
        <p><a href="/">Leave</a></p>
        ''' % (message)
    return page


@APP.route('/purchase', methods=['POST'])
def purchase():
    """ user submitted form from main page """
    credential = OAuth2Credentials.from_json(session['credential'])

    if request.form.get ('visit', False):
        return redirect(GLOEBIT.visit_uri +
                        '?return-to=' +
                        urllib.quote(url_for('main', _external=True)) +
                        '&r=' + urllib.quote(CLIENT_KEY))

    character_id = session[ 'character-id' ]

    for name in ALL_PRODUCTS:
        try:
            if request.form.get ('user-grant-%s' % name, False):
                GLOEBIT.grant_user_product (credential, name)
                return redirect(url_for('main', **{'msg': "granted " + name}))
            if request.form.get ('character-grant-%s' % name, False):
                GLOEBIT.grant_character_product \
                        (credential, character_id, name)
                return redirect(url_for('main', **{'msg': "granted " + name}))

            if request.form.get ('user-consume-%s' % name, False):
                GLOEBIT.consume_user_product (credential, name)
                return redirect(url_for('main', **{'msg': "consume " + name}))
            if request.form.get ('character-consume-%s' % name, False):
                GLOEBIT.consume_character_product \
                        (credential, character_id, name)
                return redirect(url_for('main', **{'msg': "consume " + name}))

            if request.form.get ('user-buy-%s' % name, False):
                GLOEBIT.purchase_user_product (credential, name)
                return redirect(url_for('main', **{'msg': "buy " + name}))
            if request.form.get ('character-buy-%s' % name, False):
                GLOEBIT.purchase_character_product \
                        (credential, character_id, name)
                return redirect(url_for('main', **{'msg': "buy " + name}))

        except gloebit.TransactFailureError as exn:
            kwargs = {'msg': name + ': ' + str (exn)}
            return redirect(url_for('main', **kwargs))
        except gloebit.AccessTokenError:
            kwargs = {'msg': "Stale token! You need to Leave and Enter again"}
            return redirect(url_for('main', **kwargs))
        except gloebit.ProductsAccessError, exn:
            kwargs = {'msg': name + ': ' + str (exn)}
            return redirect(url_for('main', **kwargs))

    return redirect(url_for('main', **{'msg': "what?"}))


if __name__ == "__main__":
    APP.run(debug=True)
