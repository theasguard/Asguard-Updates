#!/usr/bin/python
"""
    Asguard Addon
    Copyright (C) 2024 MrBlamo

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
import socket
import urllib.request
import urllib.parse
import random
import threading
import os
import json
import urllib
import kodi
import log_utils
from asguard_lib import image_scraper
from asguard_lib import worker_pool
from http.server import SimpleHTTPRequestHandler, HTTPServer
import logging

logging.basicConfig(level=logging.DEBUG)
logger = log_utils.Logger.get_logger(__name__)

class ValidationError(Exception):
    pass

class ImageProxy(object):
    def __init__(self, host=None):
        self.host = '127.0.0.1' if host is None else host
        self.port = int(kodi.get_setting('proxy_port') or self._get_port())
        self.svr_thread = None
        self.httpd = None
    
    @property
    def running(self):
        try: 
            res = urllib.request.urlopen('http://%s:%s/ping' % (self.host, self.port)).read()
            logging.debug(res)
        except: 
            res = ''
        return res == b'OK'
    
    def start_proxy(self):
        if not self.running:
            self.svr_thread = threading.Thread(target=self.__run)
            self.svr_thread.daemon = True
            self.svr_thread.start()
            logger.log('Proxy thread started.', log_utils.LOGNOTICE)
        else:
            logger.log('Proxy is already running.', log_utils.LOGWARNING)

    def stop_proxy(self):
        if self.httpd is not None:
            self.httpd.shutdown()
            logger.log('HTTP server shutdown initiated.', log_utils.LOGNOTICE)
        
        if self.svr_thread is not None:
            logger.log('Reaping proxy thread: %s' % (self.svr_thread))
            self.svr_thread.join()
            self.svr_thread = None
            logger.log('Proxy thread reaped.', log_utils.LOGNOTICE)

    def __run(self):
        server_address = (self.host, self.port)
        logger.log('Attempting to start Image Proxy: %s:%s' % (server_address), log_utils.LOGNOTICE)
        try:
            self.httpd = MyHTTPServer(server_address, MyRequestHandler)
            logger.log('Image Proxy started successfully', log_utils.LOGNOTICE)
            self.httpd.serve_forever()
        except Exception as e:
            logger.log('Failed to start Image Proxy: %s' % str(e), log_utils.LOGERROR)

    @staticmethod
    def _get_port():
        def is_port_available(port):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                return s.connect_ex(('127.0.0.1', port)) != 0

        port = random.randint(10000, 65535)
        while not is_port_available(port):
            port = random.randint(10000, 65535)
        
        kodi.set_setting('proxy_port', str(port))
        return port

class MyHTTPServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, bind_and_activate=True):
        self._wp = worker_pool.WorkerPool(max_workers=90)
        HTTPServer.__init__(self, server_address, RequestHandlerClass, bind_and_activate)
        
    def process_request(self, request, client_address):
        self._wp.request(func=self._process_request, args=(request, client_address))
        try: 
            self._wp.receive(0)
        except worker_pool.Empty: 
            pass
    
    def _process_request(self, request, client_address):
        try:
            HTTPServer.process_request(self, request, client_address)
        except IOError as e:
            logging.debug(e)
            logger.log('Image Proxy Error: (%s) %s - %s' % (threading.current_thread().getName(), type(e), e), log_utils.LOGDEBUG)
    
    def server_close(self):
        try:
            workers = self._wp.close()
        except:
            try: 
                worker_pool.reap_workers(workers, None)
            except UnboundLocalError: 
                pass
        HTTPServer.server_close(self)
        
class MyRequestHandler(SimpleHTTPRequestHandler):
    proxy_cache = {}
    LOG_FILE = kodi.translate_path(os.path.join(kodi.get_profile(), 'proxy.log'))
    try: 
        log_fd = open(LOG_FILE, 'w')
    except: 
        log_fd = None
    lock = threading.Lock()
    ping_required = {}

    base_req = ['video_type', 'trakt_id', 'video_ids']
    clear_required = {
        '': base_req,
        'Season': base_req + ['season'],
        'Episode': base_req + ['season', 'episode'],
    }
    base_req = base_req[:] + ['image_type']
    image_required = {
        '': base_req,
        'Season': base_req + ['season'],
        'Episode': base_req + ['season', 'episode'],
        'person': base_req + ['name', 'person_ids']
    }
    required = {'/ping': ping_required, '/': image_required, '/clear': clear_required}
    
    def _set_headers(self, code=200):
        self.send_response(code)
        self.end_headers()
        
    def __redirect(self, url):
        self.send_response(301)
        self.send_header('Location', url)
        self.end_headers()
        
    def log_message(self, format, *args):
        if self.log_fd is not None:
            self.log_fd.write('[%s] (%s) %s\n' % (self.log_date_time_string(), threading.current_thread().getName(), format % (args)))
        
    def do_HEAD(self):
        return self.do_GET()
        
    def do_POST(self):
        self._set_headers(400)
    
    def do_GET(self):
        try:
            action, fields = self.__validate(self.path)
            if action == '/ping':
                self._set_headers()
                self.wfile.write(b'OK')
                return
            else:
                key = (fields['video_type'], fields['trakt_id'], fields.get('season'), fields.get('episode'))
                if action == '/clear':
                    with self.lock:
                        if key in self.proxy_cache:
                            del self.proxy_cache[key]
                        self._set_headers()
                        self.wfile.write(b'OK')
                        return
                else:
                    with self.lock:
                        if key in self.proxy_cache:
                            images = self.proxy_cache[key]
                        else:
                            video_ids = json.loads(fields['video_ids'])
                            if fields['video_type'] == image_scraper.OBJ_PERSON:
                                person_ids = json.loads(fields['person_ids'])
                                person = {'person': {'name': fields['name'], 'ids': person_ids}}
                                images = image_scraper.scrape_person_images(video_ids, person)
                            else:
                                images = image_scraper.scrape_images(fields['video_type'], video_ids, fields.get('season', ''), fields.get('episode', ''))
                            self.proxy_cache[key] = images
                    
                    image_url = images[fields['image_type']]
                    if image_url is None:
                        self._set_headers()
                    elif image_url.startswith('http'):
                        self.__redirect(image_url)
                    else:
                        self._set_headers()
                        if self.command == 'GET':
                            with open(image_url, 'rb') as f:
                                self.wfile.write(f.read())
        except ValidationError as e:
            self.__send_error(e)
    
    def __validate(self, path):
        action = path.split('?')[0]
        params = self.parse_query(path)

        if action not in self.required:
            raise ValidationError('Unrecognized Action: %s' % (action))
        
        if '' in self.required[action]:
            required = self.required[action][''][:]
            for key in self.required[action]['']:
                if key in params: required.remove(key)
        
            if required:
                raise ValidationError('Missing Base Parameters: %s' % (', '.join(required)))
        
        if 'video_type' in params:
            video_type = params['video_type']
            if video_type in self.required[action]:
                required = self.required[action][video_type][:]
                for key in self.required[action][video_type]:
                    if key in params: required.remove(key)
        
                if required:
                    raise ValidationError('Missing Sub Parameters: %s' % (', '.join(required)))
        
        return action, params
    
    def __send_error(self, msg):
        self.send_error(400, str(msg))
    
    @staticmethod
    def parse_query(path):
        q = {}
        query = urllib.parse.urlparse(path).query
        if query.startswith('?'): query = query[1:]
        queries = urllib.parse.parse_qs(query)
        for key in queries:
            if len(queries[key]) == 1:
                q[key] = urllib.parse.unquote(queries[key][0])
            else:
                q[key] = queries[key]
        return q
