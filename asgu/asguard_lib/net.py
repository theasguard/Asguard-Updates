# -*- coding: utf-8 -*-
"""
    Asguard RD Addon
    Copyright (C) 2018 Thor

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

import http.cookiejar as cookielib
import gzip
import re
import io
import urllib.parse
import urllib.request
import socket

# Set Global timeout - Useful for slow connections and Putlocker.
socket.setdefaulttimeout(30)

class HeadRequest(urllib.request.Request):
    '''A Request class that sends HEAD requests'''
    def get_method(self):
        return 'HEAD'

class Net:
    '''
    This class wraps :mod:`urllib.request` and provides an easy way to make http
    requests while taking care of cookies, proxies, gzip compression and 
    character encoding.
    
    Example::
    
        from asguard_lib.net import Net
        net = Net()
        response = net.http_GET('http://xbmc.org')
        print(response.content)
    '''
    
    _cj = cookielib.LWPCookieJar()
    _proxy = None
    _user_agent = 'Mozilla/5.0 (Windows NT 6.1; rv:32.0) Gecko/20100101 Firefox/32.0'
    _http_debug = False
    
    
    def __init__(self, cookie_file='', proxy='', user_agent='', 
                 http_debug=False):
        '''
        Kwargs:
            cookie_file (str): Full path to a file to be used to load and save
            cookies to.
            
            proxy (str): Proxy setting (eg. 
            ``'http://user:pass@example.com:1234'``)
            
            user_agent (str): String to use as the User Agent header. If not 
            supplied the class will use a default user agent (chrome)
            
            http_debug (bool): Set ``True`` to have HTTP header info written to
            the Kodi log for all requests.
        '''
        if cookie_file:
            self.set_cookies(cookie_file)
        if proxy:
            self.set_proxy(proxy)
        if user_agent:
            self.set_user_agent(user_agent)
        self._http_debug = http_debug
        self._update_opener()
        
    
    def set_cookies(self, cookie_file):
        '''
        Set the cookie file and try to load cookies from it if it exists.
        
        Args:
            cookie_file (str): Full path to a file to be used to load and save
            cookies to.
        '''
        try:
            self._cj.load(cookie_file, ignore_discard=True)
            self._update_opener()
            return True
        except:
            return False
        
    
    def get_cookies(self):
        '''Returns A dictionary containing all cookie information by domain.'''
        return self._cj._cookies


    def save_cookies(self, cookie_file):
        '''
        Saves cookies to a file.
        
        Args:
            cookie_file (str): Full path to a file to save cookies to.
        '''
        self._cj.save(cookie_file, ignore_discard=True)        

        
    def set_proxy(self, proxy):
        '''
        Args:
            proxy (str): Proxy setting (eg. 
            ``'http://user:pass@example.com:1234'``)
        '''
        self._proxy = proxy
        self._update_opener()

        
    def get_proxy(self):
        '''Returns string containing proxy details.'''
        return self._proxy
        
        
    def set_user_agent(self, user_agent):
        '''
        Args:
            user_agent (str): String to use as the User Agent header.
        '''
        self._user_agent = user_agent

        
    def get_user_agent(self):
        '''Returns user agent string.'''
        return self._user_agent


    def _update_opener(self):
        '''
        Builds and installs a new opener to be used by all future calls to 
        :func:`urllib.request.urlopen`.
        '''
        if self._http_debug:
            http = urllib.request.HTTPHandler(debuglevel=1)
        else:
            http = urllib.request.HTTPHandler()
            
        if self._proxy:
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._cj),
                                                 urllib.request.ProxyHandler({'http': 
                                                                              self._proxy}), 
                                                 urllib.request.HTTPBasicAuthHandler(),
                                                 http)
        
        else:
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._cj),
                                                 urllib.request.HTTPBasicAuthHandler(),
                                                 http)
        urllib.request.install_opener(opener)
        

    def http_GET(self, url, headers={}, compression=True):
        '''
        Perform an HTTP GET request.
        
        Args:
            url (str): The URL to GET.
            
        Kwargs:
            headers (dict): A dictionary describing any headers you would like
            to add to the request. (eg. ``{'X-Test': 'testing'}``)

            compression (bool): If ``True`` (default), try to use gzip 
            compression.
            
        Returns:
            An :class:`HttpResponse` object containing headers and other 
            meta-information about the page and the page content.
        '''
        return self._fetch(url, headers=headers, compression=compression)
        

    def http_POST(self, url, form_data, headers={}, compression=True):
        '''
        Perform an HTTP POST request.
        
        Args:
            url (str): The URL to POST.
            
            form_data (dict): A dictionary of form data to POST.
            
        Kwargs:
            headers (dict): A dictionary describing any headers you would like
            to add to the request. (eg. ``{'X-Test': 'testing'}``)

            compression (bool): If ``True`` (default), try to use gzip 
            compression.

        Returns:
            An :class:`HttpResponse` object containing headers and other 
            meta-information about the page and the page content.
        '''
        return self._fetch(url, form_data, headers=headers,
                           compression=compression)

    
    def http_HEAD(self, url, headers={}):
        '''
        Perform an HTTP HEAD request.
        
        Args:
            url (str): The URL to GET.
        
        Kwargs:
            headers (dict): A dictionary describing any headers you would like
            to add to the request. (eg. ``{'X-Test': 'testing'}``)
        
        Returns:
            An :class:`HttpResponse` object containing headers and other 
            meta-information about the page.
        '''
        req = HeadRequest(url)
        req.add_header('User-Agent', self._user_agent)
        for k, v in headers.items():
            req.add_header(k, v)
        response = urllib.request.urlopen(req)
        return HttpResponse(response)


    def _fetch(self, url, form_data={}, headers={}, compression=True):
        '''
        Perform an HTTP GET or POST request.
        
        Args:
            url (str): The URL to GET or POST.
            
            form_data (dict): A dictionary of form data to POST. If empty, the 
            request will be a GET, if it contains form data it will be a POST.
            
        Kwargs:
            headers (dict): A dictionary describing any headers you would like
            to add to the request. (eg. ``{'X-Test': 'testing'}``)

            compression (bool): If ``True`` (default), try to use gzip 
            compression.

        Returns:
            An :class:`HttpResponse` object containing headers and other 
            meta-information about the page and the page content.
        '''
        encoding = ''
        req = urllib.request.Request(url)
        if form_data:
            form_data = urllib.parse.urlencode(form_data).encode('utf-8')
            req = urllib.request.Request(url, form_data)
        req.add_header('User-Agent', self._user_agent)
        for k, v in headers.items():
            req.add_header(k, v)
        if compression:
            req.add_header('Accept-Encoding', 'gzip')
        response = urllib.request.urlopen(req)
        return HttpResponse(response)



class HttpResponse:
    '''
    This class represents a response from an HTTP request.
    
    The content is examined and every attempt is made to properly encode it to
    Unicode.
    
    .. seealso::
        :meth:`Net.http_GET`, :meth:`Net.http_HEAD` and :meth:`Net.http_POST` 
    '''
    
    content = ''
    '''Unicode encoded string containing the body of the response.'''
    
    
    def __init__(self, response):
        '''
        Args:
            response (:class:`http.client.HTTPResponse`): The object returned by a call
            to :func:`urllib.request.urlopen`.
        '''
        self._response = response
        html = response.read()
        try:
            if response.headers['content-encoding'].lower() == 'gzip':
                html = gzip.GzipFile(fileobj=io.BytesIO(html)).read()
        except:
            pass
        
        try:
            content_type = response.headers['content-type']
            if 'charset=' in content_type:
                encoding = content_type.split('charset=')[-1]
        except:
            pass

        r = re.search('<meta\s+http-equiv="Content-Type"\s+content="(?:.+?);' +
                      '\s+charset=(.+?)"', html.decode('utf-8'), re.IGNORECASE)
        if r:
            encoding = r.group(1) 
                   
        try:
            html = html.decode(encoding)
        except:
            pass
            
        self.content = html
    
    
    def get_headers(self):
        '''Returns a List of headers returned by the server.'''
        return self._response.info().headers
    
        
    def get_url(self):
        '''
        Return the URL of the resource retrieved, commonly used to determine if 
        a redirect was followed.
        '''
        return self._response.geturl()
