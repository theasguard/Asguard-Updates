def __call_trakt(self, url, method=None, data=None, params=None, auth=True, cache_limit=.25, cached=True):
    res_headers = {}
    if not cached:
        cache_limit = 0
    if self.offline:
        db_cache_limit = int(time.time()) / 60 / 60
    else:
        db_cache_limit = max(cache_limit, 8)

    json_data = json.dumps(data) if data else None
    logger.log(f'***Trakt Call: {url}, data: {json_data} cache_limit: {cache_limit} cached: {cached}', log_utils.LOGDEBUG)

    headers = {
        'Content-Type': 'application/json',
        'trakt-api-key': V2_API_KEY,
        'trakt-api-version': 2
    }
    url = f'{self.protocol}{BASE_URL}{url}'
    if params:
        url += '?' + urllib_parse.urlencode(params)

    db_connection = self.__get_db_connection()
    created, cached_headers, cached_result = db_connection.get_cached_url(url, json_data, db_cache_limit)
    if cached_result and (self.offline or (time.time() - created) < (60 * 60 * cache_limit)):
        result = cached_result
        res_headers = dict(cached_headers)
        logger.log(f'***Using cached result for: {url}', log_utils.LOGDEBUG)
    else:
        auth_retry = False
        while True:
            try:
                if auth:
                    headers['Authorization'] = f'Bearer {self.token}'
                logger.log(f'***Trakt Call: {url}, header: {headers}, data: {json_data} cache_limit: {cache_limit} cached: {cached}', log_utils.LOGDEBUG)
                request = urllib_request.Request(url, data=json_data.encode('utf-8') if json_data else None, headers=headers)
                if method:
                    request.get_method = lambda: method.upper()

                response = urllib_request.urlopen(request, timeout=self.timeout)
                result = response.read().decode('utf-8')
                logger.log(f'***Trakt Response: {result}', log_utils.LOGDEBUG)

                db_connection.cache_url(url, result, json_data, response.info().items())
                break
            except (ssl.SSLError, socket.timeout) as e:
                logger.log(f'Socket Timeout or SSL Error occurred: {e}', log_utils.LOGWARNING)
                if cached_result:
                    result = cached_result
                    logger.log(f'Temporary Trakt Error ({e}). Using Cached Page Instead.', log_utils.LOGWARNING)
                else:
                    raise TransientTraktError(f'Temporary Trakt Error: {e}')
            except urllib_error.URLError as e:
                if isinstance(e, urllib_error.HTTPError):
                    if e.code in TEMP_ERRORS:
                        if cached_result:
                            result = cached_result
                            logger.log(f'Temporary Trakt Error ({e}). Using Cached Page Instead.', log_utils.LOGWARNING)
                            break
                        else:
                            raise TransientTraktError(f'Temporary Trakt Error: {e}')
                    elif e.code in {401, 405}:
                        if 'X-Private-User' in e.headers and e.headers.get('X-Private-User') == 'true':
                            raise TraktAuthError(f'Object is No Longer Available ({e.code})')
                        elif auth_retry or url.endswith('/oauth/token'):
                            self.token = None
                            kodi.set_setting('trakt_oauth_token', '')
                            kodi.set_setting('trakt_refresh_token', '')
                            raise TraktAuthError(f'Trakt Call Authentication Failed ({e.code})')
                        else:
                            result = self.refresh_token(kodi.get_setting('trakt_refresh_token'))
                            self.token = result['access_token']
                            kodi.set_setting('trakt_oauth_token', result['access_token'])
                            kodi.set_setting('trakt_refresh_token', result['refresh_token'])
                            auth_retry = True
                    elif e.code == 404:
                        raise TraktNotFoundError(f'Object Not Found ({e.code}): {url}')
                    else:
                        raise
                elif isinstance(e.reason, (socket.timeout, ssl.SSLError)):
                    if cached_result:
                        result = cached_result
                        logger.log(f'Temporary Trakt Error ({e}). Using Cached Page Instead', log_utils.LOGWARNING)
                        break
                    else:
                        raise TransientTraktError(f'Temporary Trakt Error: {e}')
                else:
                    raise TraktError(f'Trakt Error: {e}')
            except Exception as e:
                logger.log(f'Unexpected error: {e}', log_utils.LOGERROR)
                raise

    try:
        if isinstance(result, bytes):
            result = result.decode('utf-8')
        js_data = utils.json_loads_as_str(result)
        if 'x-sort-by' in res_headers and 'x-sort-how' in res_headers:
            js_data = utils2.sort_list(res_headers['x-sort-by'], res_headers['x-sort-how'], js_data)
    except ValueError:
        js_data = ''
        if result:
            logger.log(f'Invalid JSON Trakt API Response: {url} - |{result}|', log_utils.LOGERROR)

    return js_data
