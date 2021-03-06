from flask import Flask, request
import libtmux
from libtmux.exc import *

from distutils import util
import sys
import six
import threading
import socket
import argparse
import logging


app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

def get_arguments():
    parser = argparse.ArgumentParser(
        description='Send input to just about any interactive command-line tool on the local network',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    required = parser.add_argument_group('required arguments')

    required.add_argument(
        '-c', '--cmd',
        required=True,
        type=str,
        help='interactive command to send input to')
    required.add_argument(
        '-w', '--window-name',
        required=True,
        type=str,
        help='tmux\'s window name')

    parser.add_argument(
        '-d', '--detach',
        action='store_true',
        help='detach from ongoing session')
    parser.add_argument(
        '-s', '--session-name', default='muxnect',
        type=str,
        help='tmux\'s session name')
    parser.add_argument(
        '-b', '--bind-address', default='127.0.0.1',
        type=str,
        help='address to bind on, local network: 0.0.0.0')
    parser.add_argument(
        '-p', '--port', default=6060,
        type=int,
        help='port number to listen on')

    return parser.parse_args()


class TmuxWindowExists(Exception):
    __module__ = Exception.__module__
    def __init__(self, message=None):
        super(TmuxWindowExists, self).__init__(message)


def port_is_busy(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        s.bind(('127.0.0.1', port))
    except socket.error as e:
        return e.errno
    finally:
        s.close()

    return 0


def query_exists(query, data):
    if query in data:
        return util.strtobool(data[query])
    else:
        return False


@app.route('/muxnect/<window_name>', methods=['POST'])
def handle_request(window_name):
    window = session.find_where({'window_name': window_name})

    enter = query_exists('enter', request.form)
    suppress_history = query_exists('suppress_history', request.form)

    pane = window.attached_pane
    if 'keys' in request.form:
        pane.send_keys(request.form['keys'],
                       enter=enter,
                       suppress_history=suppress_history)

    if query_exists('kill', request.form):
        try:
            window.kill_window()
        except LibTmuxException:
            pass

    return '200'


def command_line():
    args = get_arguments()
    session_name = args.session_name
    window_name = args.window_name
    detach = args.detach
    cmd = args.cmd
    bind_address = args.bind_address
    port = args.port

    socket_code =  port_is_busy(port)
    if socket_code:
        raise OSError('[Errno {}] Cannot start web server on port {}'.format(socket_code, port))

    global session

    try:
        server = libtmux.Server()
        session = server.new_session(session_name)
        window = session.new_window(window_name)
        session.kill_window('@0')

    except TmuxSessionExists:
        session = server.find_where({'session_name': session_name})

        if session.find_where({'window_name': window_name}):
            session.kill_session()
            message = 'Window named {0} exists in session named {1}'.format(
                       window_name, session_name)
            six.raise_from(TmuxWindowExists(message), None)

        window = session.new_window(window_name)

    pane = window.attached_pane
    pane.send_keys(cmd)

    url = 'http://{0}:{1}/{2}/{3}'.format(bind_address, port, session_name, window_name)
    web_app_args = { 'host'    : bind_address,
                     'port'    : port,
                     'threaded': True }

    web_app = threading.Thread(target=app.run, kwargs=web_app_args)

    web_app.start()
    print('Listening on {}'.format(url))
    print('Press CTRL+C to exit muxnect')

    if not detach:
        session.attach_session()


if __name__ == '__main__':

    command_line()
