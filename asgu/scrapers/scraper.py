"""
    Asguard Addon
    Copyright (C) 2014 Thor

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
import abc
import datetime
import gzip
import os
import re
import urllib.error
import http.cookiejar
from io import StringIO

from asguard_lib import cloudflare
from asguard_lib import cf_captcha
import kodi
import log_utils  # @UnusedImport

import six
from six.moves import urllib_request, urllib_parse, urllib_error
from six.moves import http_cookiejar as cookielib
from asguard_lib import scraper_utils
from asguard_lib.constants import FORCE_NO_MATCH, Q_ORDER, SHORT_MONS, VIDEO_TYPES, DEFAULT_TIMEOUT
from asguard_lib.db_utils import DB_Connection
from asguard_lib.utils2 import i18n, ungz
import xbmcgui

try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)

logger = log_utils.Logger.get_logger()

BASE_URL = ''
CAPTCHA_BASE_URL = 'http://www.google.com/recaptcha/api'
COOKIEPATH = kodi.translate_path(kodi.get_profile())
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
MAX_RESPONSE = 1024 * 1024 * 5
CF_CAPCHA_ENABLED = kodi.get_setting('cf_captcha') == 'true'

class ScrapeError(Exception):
    pass

class NoRedirection(urllib_request.HTTPErrorProcessor):
    def http_response(self, request, response):  # @UnusedVariable
        logger.log('Stopping Redirect', log_utils.LOGDEBUG)
        return response

    https_response = http_response

abstractstaticmethod = abc.abstractmethod
class abstractclassmethod(classmethod):

    __isabstractmethod__ = True

    def __init__(self, callable):
        callable.__isabstractmethod__ = True
        super(abstractclassmethod, self).__init__(callable)


class Scraper(object):
    __metaclass__ = abc.ABCMeta
    base_url = BASE_URL
    __db_connection = None
    worker_id = None
    debrid_resolvers = resolveurl
    row_pattern = r'\s*<a\s+href="(?P<link>[^"]+)">(?P<title>[^<]+)</a>\s+(?P<date>\d+-[a-zA-Z]+-\d+ \d+:\d+)\s+(?P<size>-|\d+)'

    def __init__(self, timeout=DEFAULT_TIMEOUT):
        self.timeout = timeout

    @abstractclassmethod
    def provides(cls):
        """
        Must return a list/set/frozenset of VIDEO_TYPES that are supported by this scraper. Is a class method so that instances of the class
        don't have to be instantiated to determine they are not useful

        * Datatypes set or frozenset are preferred as existence checking is faster with sets
        """
        raise NotImplementedError

    @abstractclassmethod
    def get_name(cls):
        """
        Must return a string that is a name that will be used through out the UI and DB to refer to urls from this source
        Should be descriptive enough to be recognized but short enough to be presented in the UI
        """
        raise NotImplementedError

    def resolve_link(self, link):
        """
        Must return a string that is a resolveurl resolvable link given a link that this scraper supports

        link: a url fragment associated with this site that can be resolved to a hoster link

        * The purpose is many streaming sites provide the actual hoster link in a separate page from link
        on the video page.
        * This method is called for the user selected source before calling resolveurl on it.
        """
        if link.startswith(('magnet:', 'http', 'https', 'ftp')) or link.endswith('.torrent'):
            return link
        else:
            return scraper_utils.urljoin(self.base_url, link)

    def format_source_label(self, item):
        """
        Must return a string that is to be the label to be used for this source in the "Choose Source" dialog

        item: one element of the list that is returned from get_sources for this scraper
        """
        label = '[%s]' % (item['quality'])

        if 'torrent' in item and item['torrent']:
            label += ' (Torrent)'

        if '4K' in item and item['4K']:
            label += ' (HD4K)'
        
        if '3D' in item and item['3D']:
            label += ' (3D)'
            
        if 'format' in item:
            label += ' (%s)' % (item['format'])
        
        if 'version' in item:
            label += ' %s' % (item['version'])
            
        label += ' %s' % (item['host'])
        
        if 'views' in item and item['views'] is not None:
            label += ' (%s views)' % (item['views'])
        
        if 'rating' in item and item['rating'] is not None:
            label += ' (%s/100)' % (item['rating'])
            
        if 'size' in item:
            label += ' (%s)' % (item['size'])

        if 'subs' in item and item['subs']:
            label += ' (%s)' % (item['subs'])
            
        if 'extra' in item:
            label += ' [%s]' % (item['extra'])
        return label

    @abc.abstractmethod
    def get_sources(self, video):
        """
        Must return a list of dictionaries that are potential link to hoster sites (or links to links to hoster sites)
        Each dictionary must contain elements of at least:
            * multi-part: True if this source is one part of a whole
            * class: a reference to an instance of the scraper itself
            * host: the hostname of the hoster
            * url: the url that is a link to a hoster, or a link to a page that this scraper can resolve to a link to a hoster
            * quality: one of the QUALITIES values, or None if unknown; users can sort sources by quality
            * views: count of the views from the site for this source or None is unknown; Users can sort sources by views
            * rating: a value between 0 and 100; 0 being worst, 100 the best, or None if unknown. Users can sort sources by rating.
            * direct: True if url is a direct link to a media file; False if not. If not present; assumption is direct
            * other keys are allowed as needed if they would be useful (e.g. for format_source_label)

        video is an object of type ScraperVideo:
            video_type: one of VIDEO_TYPES for whatever the sources should be for
            title: the title of the tv show or movie
            year: the year of the tv show or movie
            season: only present for tv shows; the season number of the video for which sources are requested
            episode: only present for tv shows; the episode number of the video for which sources are requested
            ep_title: only present for tv shows; the episode title if available
        """
        raise NotImplementedError

    def get_url(self, video):
        """
        Must return a url for the site this scraper is associated with that is related to this video.

        video is an object of type ScraperVideo:
            video_type: one of VIDEO_TYPES this url is for (e.g. EPISODE urls might be different than TVSHOW urls)
            title: the title of the tv show or movie
            year: the year of the tv show or movie
            season: only present for season or episode VIDEO_TYPES; the season number for the url being requested
            episode: only present for season or episode VIDEO_TYPES; the episode number for the url being requested
            ep_title: only present for tv shows; the episode title if available

        * Generally speaking, domain should not be included
        """
        return self._default_get_url(video)

    @abc.abstractmethod
    def search(self, video_type, title, year, season=''):
        """
        Must return a list of results returned from the site associated with this scraper when doing a search using the input parameters

        If it does return results, it must be a list of dictionaries. Each dictionary must contain at least the following:
            * title: title of the result
            * year: year of the result
            * url: a url fragment that is the url on the site associated with this scraper for this season result item

        video_type: one of the VIDEO_TYPES being searched for. Only tvshows and movies are expected generally
        title: the title being search for
        year: the year being search for
        season: the season being searched for (only required if video_type == VIDEO_TYPES.SEASON)

        * Method must be provided, but can raise NotImplementedError if search not available on the site
        """
        raise NotImplementedError

    @classmethod
    def get_settings(cls):
        """
        Returns a list of settings to be used for this scraper. Settings are automatically checked for updates every time scrapers are imported
        The list returned by each scraper is aggregated into a big settings.xml string, and then if it differs from the current settings xml in the Scrapers category
        the existing settings.xml fragment is removed and replaced by the new string
        """
        name = cls.get_name()
        return [
            '         <setting id="%s-enable" type="bool" label="%s %s" default="true" visible="true"/>' % (name, name, i18n('enabled')),
            '         <setting id="%s-base_url" type="text" label="    %s" default="%s" visible="eq(-1,true)"/>' % (name, i18n('base_url'), cls.base_url),
            '         <setting id="%s-sub_check" type="bool" label="    %s" default="true" visible="eq(-2,true)"/>' % (name, i18n('page_existence')),
        ]

    @classmethod
    def has_proxy(cls):
        return False
    
    def _default_get_url(self, video):
        url = None
        temp_video_type = video.video_type
        if video.video_type == VIDEO_TYPES.EPISODE:
            if VIDEO_TYPES.TVSHOW in self.provides():
                temp_video_type = VIDEO_TYPES.TVSHOW
            elif VIDEO_TYPES.SEASON in self.provides():
                temp_video_type = VIDEO_TYPES.SEASON

        season = video.season if temp_video_type == VIDEO_TYPES.SEASON else ''
        if temp_video_type != VIDEO_TYPES.EPISODE:
            result = self.db_connection().get_related_url(temp_video_type, video.title, video.year, self.get_name(), season)
            if result:
                url = result[0][0]
                logger.log('Got local related url: |%s|%s|%s|%s|%s|%s|' % (temp_video_type, video.title, video.year, season, self.get_name(), url), log_utils.LOGDEBUG)
            else:
                results = self.search(temp_video_type, video.title, video.year, season)
                if results:
                    url = results[0]['url']
                    self.db_connection().set_related_url(temp_video_type, video.title, video.year, self.get_name(), url, season)

        if isinstance(url, str): url = url.encode('utf-8')
        if video.video_type == VIDEO_TYPES.EPISODE:
            if url == FORCE_NO_MATCH:
                url = None
            elif url or temp_video_type == VIDEO_TYPES.EPISODE:
                result = self.db_connection().get_related_url(VIDEO_TYPES.EPISODE, video.title, video.year, self.get_name(), video.season, video.episode)
                if result:
                    url = result[0][0]
                    if isinstance(url, str): url = url.encode('utf-8')
                    logger.log('Got local related url: |%s|%s|%s|' % (video, self.get_name(), url), log_utils.LOGDEBUG)
                else:
                    url = self._get_episode_url(url, video)
                    if url:
                        self.db_connection().set_related_url(VIDEO_TYPES.EPISODE, video.title, video.year, self.get_name(), url, video.season, video.episode)

        return url

    def _http_get(self, url, params=None, data=None, multipart_data=None, headers=None, cookies=None, allow_redirect=True, method=None, require_debrid=False, read_error=False, cache_limit=8):
        html = self._cached_http_get(url, self.base_url, self.timeout, params=params, data=data, multipart_data=multipart_data,
                                     headers=headers, cookies=cookies, allow_redirect=allow_redirect, method=method, require_debrid=require_debrid,
                                     read_error=read_error, cache_limit=cache_limit)
        sucuri_cookie = scraper_utils.get_sucuri_cookie(html)
        if sucuri_cookie:
            logger.log('Setting sucuri cookie: %s' % (sucuri_cookie), log_utils.LOGDEBUG)
            if cookies is not None:
                cookies.update(sucuri_cookie)
            else:
                cookies = sucuri_cookie
            html = self._cached_http_get(url, self.base_url, self.timeout, params=params, data=data, multipart_data=multipart_data,
                                         headers=headers, cookies=cookies, allow_redirect=allow_redirect, method=method, require_debrid=require_debrid,
                                         read_error=read_error, cache_limit=0)
        return html
    
    def _cached_http_get(self, url, base_url, timeout, params=None, data=None, multipart_data=None, headers=None, cookies=None, allow_redirect=True,
                         method=None, require_debrid=False, read_error=False, cache_limit=8):
        if require_debrid:
            if Scraper.debrid_resolvers is None:
                Scraper.debrid_resolvers = [resolver for resolver in resolveurl.relevant_resolvers() if resolver.isUniversal()]
            if not Scraper.debrid_resolvers:
                logger.log(f'{self.__module__} requires debrid: {Scraper.debrid_resolvers}', log_utils.LOGDEBUG)
                return ''
                
        if cookies is None: cookies = {}
        if timeout == 0: timeout = None
        if headers is None: headers = {}
        if url.startswith('//'): url = 'http:' + url
        referer = headers.get('Referer', base_url)
        if params:
            if url == base_url and not url.endswith('/'):
                url += '/'
            
            parts = urllib_parse.urlparse(url)
            if parts.query:
                params.update(scraper_utils.parse_query(url))
                url = urllib_parse.urlunparse((parts.scheme, parts.netloc, parts.path, parts.params, '', parts.fragment))
                
            url += '?' + urllib_parse.urlencode(params)
        logger.log(f'Getting Url: {url} cookie=|{cookies}| data=|{data}| extra headers=|{headers}|', log_utils.LOGDEBUG)
        if data is not None:
            if isinstance(data, str):
                data = data
            else:
                data = urllib_parse.urlencode(data, True)

        if multipart_data is not None:
            headers['Content-Type'] = 'multipart/form-data; boundary=X-X-X'
            data = multipart_data

        _created, _res_header, html = self.db_connection().get_cached_url(url, data, cache_limit)
        if html:
            logger.log(f'Returning cached result for: {url}', log_utils.LOGDEBUG)
            return html

        try:
            self.cj = self._set_cookies(base_url, cookies)
            if isinstance(url, str): url = url.encode('utf-8')
            request = urllib_request.Request(url, data=data)
            headers = headers.copy()
            request.add_header('User-Agent', scraper_utils.get_ua())
            request.add_header('Accept', '*/*')
            request.add_header('Accept-Encoding', 'gzip')
            request.add_unredirected_header('Host', request.get_host())
            if referer: request.add_unredirected_header('Referer', referer)
            headers.pop('Referer', None)
            headers.pop('Host', None)
            for key, value in headers.items(): request.add_header(key, value)
            self.cj.add_cookie_header(request)
            if not allow_redirect:
                opener = urllib_request.build_opener(NoRedirection)
                urllib_request.install_opener(opener)
            else:
                opener = urllib_request.build_opener(urllib_request.HTTPRedirectHandler)
                urllib_request.install_opener(opener)
                opener2 = urllib_request.build_opener(urllib_request.HTTPCookieProcessor(self.cj))
                urllib_request.install_opener(opener2)

            if method is not None: request.get_method = lambda: method.upper()
            response = urllib_request.urlopen(request, timeout=timeout)
            self.cj.extract_cookies(response, request)
            if kodi.get_setting('cookie_debug') == 'true':
                logger.log(f'Response Cookies: {url} - {scraper_utils.cookies_as_str(self.cj)}', log_utils.LOGDEBUG)
            self.cj._cookies = scraper_utils.fix_bad_cookies(self.cj._cookies)
            self.cj.save(ignore_discard=True)
            if not allow_redirect and (response.getcode() in [301, 302, 303, 307] or response.info().get('Refresh')):
                if response.info().get('Refresh') is not None:
                    refresh = response.info().get('Refresh')
                    return refresh.split(';')[-1].split('url=')[-1]
                else:
                    redir_url = response.info().get('Location')
                    if redir_url.startswith('='):
                        redir_url = redir_url[1:]
                    return redir_url
            
            content_length = response.info().get('Content-Length', 0)
            if int(content_length) > MAX_RESPONSE:
                logger.log(f'Response exceeded allowed size. {url} => {content_length} / {MAX_RESPONSE}', log_utils.LOGWARNING)
            
            if method == 'HEAD':
                return ''
            else:
                if response.info().get('Content-Encoding') == 'gzip':
                    html = ungz(response.read(MAX_RESPONSE))
                else:
                    html = response.read(MAX_RESPONSE)
        except urllib.error.HTTPError as e:
            if e.info().get('Content-Encoding') == 'gzip':
                html = ungz(e.read(MAX_RESPONSE))
            else:
                html = e.read(MAX_RESPONSE)
                
            if CF_CAPCHA_ENABLED and e.code == 403 and 'cf-captcha-bookmark' in html:
                html = cf_captcha.solve(url, self.cj, scraper_utils.get_ua(), self.get_name())
                if not html:
                    return ''
            elif e.code == 503 and 'cf-browser-verification' in html:
                html = cloudflare.solve(url, self.cj, scraper_utils.get_ua(), extra_headers=headers)
                if not html:
                    return ''
            else:
                logger.log(f'Error ({str(e)}) during scraper http get: {url}', log_utils.LOGWARNING)
                if not read_error:
                    return ''
        except Exception as e:
            logger.log(f'Error ({str(e)}) during scraper http get: {url}', log_utils.LOGWARNING)
            return ''

        self.db_connection().cache_url(url, html, data)
        return html

    def _set_cookies(self, base_url, cookies):
        cookie_file = os.path.join(COOKIEPATH, f'{self.get_name()}_cookies.lwp')
        cj = http.cookiejar.LWPCookieJar(cookie_file)
        try: cj.load(ignore_discard=True)
        except: pass
        if kodi.get_setting('cookie_debug') == 'true':
            logger.log(f'Before Cookies: {self} - {scraper_utils.cookies_as_str(cj)}', log_utils.LOGDEBUG)
        domain = urllib_parse.urlsplit(base_url).hostname
        for key in cookies:
            c = http.cookiejar.Cookie(0, key, str(cookies[key]), port=None, port_specified=False, domain=domain, domain_specified=True,
                                 domain_initial_dot=False, path='/', path_specified=True, secure=False, expires=None, discard=False, comment=None,
                                 comment_url=None, rest={})
            cj.set_cookie(c)
        cj.save(ignore_discard=True)
        if kodi.get_setting('cookie_debug') == 'true':
            logger.log(f'After Cookies: {self} - {scraper_utils.cookies_as_str(cj)}', log_utils.LOGDEBUG)
        return cj

    def _do_recaptcha(self, key, tries=None, max_tries=None):
        challenge_url = f'{CAPTCHA_BASE_URL}/challenge?k={key}'
        html = self._cached_http_get(challenge_url, CAPTCHA_BASE_URL, timeout=DEFAULT_TIMEOUT, cache_limit=0)
        match = re.search(r"challenge\s+:\s+'([^']+)", html)
        captchaimg = f'http://www.google.com/recaptcha/api.js/image?c={match.group(1)}'
        img = xbmcgui.ControlImage(450, 0, 400, 130, captchaimg)
        wdlg = xbmcgui.WindowDialog()
        wdlg.addControl(img)
        wdlg.show()
        header = 'Type the words in the image'
        if tries and max_tries:
            header += f' (Try: {tries}/{max_tries})'
        solution = kodi.get_keyboard(header)
        if not solution:
            raise Exception('You must enter text in the image to access video')
        wdlg.close()
        return {'recaptcha_challenge_field': match.group(1), 'recaptcha_response_field': solution}

    def _default_get_episode_url(self, html, video, episode_pattern, title_pattern='', airdate_pattern=''):
        logger.log(f'Default Episode Url: |{self.get_name()}|{video}|', log_utils.LOGDEBUG)
        if not html:
            return
        
        try:
            html = html[0].content
        except AttributeError:
            pass
        force_title = scraper_utils.force_title(video)
        if not force_title:
            if episode_pattern:
                match = re.search(episode_pattern, html, re.DOTALL | re.I)
                if match:
                    return scraper_utils.pathify_url(match.group(1))

            if kodi.get_setting('airdate-fallback') == 'true' and airdate_pattern and video.ep_airdate:
                airdate_pattern = airdate_pattern.replace('{year}', str(video.ep_airdate.year))
                airdate_pattern = airdate_pattern.replace('{month}', str(video.ep_airdate.month))
                airdate_pattern = airdate_pattern.replace('{p_month}', f'{video.ep_airdate.month:02d}')
                airdate_pattern = airdate_pattern.replace('{month_name}', MONTHS[video.ep_airdate.month - 1])
                airdate_pattern = airdate_pattern.replace('{short_month}', SHORT_MONS[video.ep_airdate.month - 1])
                airdate_pattern = airdate_pattern.replace('{day}', str(video.ep_airdate.day))
                airdate_pattern = airdate_pattern.replace('{p_day}', f'{video.ep_airdate.day:02d}')
                logger.log(f'Air Date Pattern: {airdate_pattern}', log_utils.LOGDEBUG)

                match = re.search(airdate_pattern, html, re.DOTALL | re.I)
                if match:
                    return scraper_utils.pathify_url(match.group(1))
        else:
            logger.log(f'Skipping S&E matching as title search is forced on: {video.trakt_id}', log_utils.LOGDEBUG)

        if (force_title or kodi.get_setting('title-fallback') == 'true') and video.ep_title and title_pattern:
            norm_title = scraper_utils.normalize_title(video.ep_title)
            for match in re.finditer(title_pattern, html, re.DOTALL | re.I):
                episode = match.groupdict()
                if norm_title == scraper_utils.normalize_title(episode['title']):
                    return scraper_utils.pathify_url(episode['url'])

    def _blog_proc_results(self, html, post_pattern, date_format, video_type, title, year):
        results = []
        search_date = ''
        search_sxe = ''
        if video_type == VIDEO_TYPES.EPISODE:
            match = re.search(r'(.*?)\s*(S\d+E\d+)\s*', title)
            if match:
                show_title, search_sxe = match.groups()
            else:
                match = re.search(r'(.*?)\s*(\d{4})[._ -]?(\d{2})[._ -]?(\d{2})\s*', title)
                if match:
                    show_title, search_year, search_month, search_day = match.groups()
                    search_date = f'{search_year}-{search_month}-{search_day}'
                    search_date = scraper_utils.to_datetime(search_date, "%Y-%m-%d").date()
                else:
                    show_title = title
        else:
            show_title = title

        today = datetime.date.today()
        for match in re.finditer(post_pattern, html, re.DOTALL):
            post_data = match.groupdict()
            post_title = post_data['post_title']
            post_title = re.sub('<[^>]*>', '', post_title)
            if 'quality' in post_data:
                post_title += f'- [{post_data["quality"]}]'

            try:
                filter_days = int(kodi.get_setting(f'{self.get_name()}-filter'))
            except ValueError:
                filter_days = 0
            if filter_days and date_format and 'date' in post_data:
                post_data['date'] = post_data['date'].strip()
                filter_days = datetime.timedelta(days=filter_days)
                post_date = scraper_utils.to_datetime(post_data['date'], date_format).date()
                if not post_date:
                    logger.log(f'Failed date Check in {self.get_name()}: |{post_data["date"]}|{date_format}|', log_utils.LOGWARNING)
                    post_date = today
                        
                if today - post_date > filter_days:
                    continue

            match_year = ''
            match_date = ''
            match_sxe = ''
            match_title = full_title = post_title
            if video_type == VIDEO_TYPES.MOVIE:
                meta = scraper_utils.parse_movie_link(post_title)
                match_year = meta['year']
            else:
                meta = scraper_utils.parse_episode_link(post_title)
                match_sxe = f'S{int(meta["season"]):02d}E{int(meta["episode"]):02d}'
                match_date = meta['airdate']

            match_title = meta['title']
            full_title = f'{meta["title"]} ({meta["height"]}p) [{meta["extra"]}]'
            norm_title = scraper_utils.normalize_title(show_title)
            match_norm_title = scraper_utils.normalize_title(match_title)
            title_match = norm_title and (match_norm_title in norm_title or norm_title in match_norm_title)
            year_match = not year or not match_year or year == match_year
            sxe_match = not search_sxe or (search_sxe == match_sxe)
            date_match = not search_date or (search_date == match_date)
            logger.log(f'Blog Results: |{match_norm_title}|{norm_title}|{title_match}| - |{year}|{match_year}|{year_match}| - |{search_date}|{match_date}|{date_match}| - |{search_sxe}|{match_sxe}|{sxe_match}| ({self.get_name()})', log_utils.LOGDEBUG)
            if title_match and year_match and date_match and sxe_match:
                quality = scraper_utils.height_get_quality(meta['height'])
                result = {'url': scraper_utils.pathify_url(post_data['url']), 'title': scraper_utils.cleanse_title(full_title), 'year': match_year, 'quality': quality}
                results.append(result)
        return results
    
    def _blog_get_url(self, video, delim='.'):
        url = None
        result = self.db_connection().get_related_url(video.video_type, video.title, video.year, self.get_name(), video.season, video.episode)
        if result:
            url = result[0][0]
            logger.log(f'Got local related url: |{video.video_type}|{video.title}|{video.year}|{self.get_name()}|{url}|', log_utils.LOGDEBUG)
        else:
            try:
                select = int(kodi.get_setting(f'{self.get_name()}-select'))
            except:
                select = 0
            if video.video_type == VIDEO_TYPES.EPISODE:
                temp_title = re.sub('[^A-Za-z0-9 ]', '', video.title)
                if not scraper_utils.force_title(video):
                    search_title = '%s S%02dE%02d' % (temp_title, int(video.season), int(video.episode))
                    if isinstance(video.ep_airdate, datetime.date):
                        fallback_search = f'{temp_title} {video.ep_airdate.strftime(f"%Y{delim}%m{delim}%d")}'
                    else:
                        fallback_search = ''
                else:
                    if not video.ep_title:
                        return None
                    search_title = f'{temp_title} {video.ep_title}'
                    fallback_search = ''
            else:
                search_title = video.title
                fallback_search = ''

            results = self.search(video.video_type, search_title, video.year)
            if not results and fallback_search:
                results = self.search(video.video_type, fallback_search, video.year)
                
            if results:
                # TODO: First result isn't always the most recent...
                best_result = results[0]
                if select != 0:
                    best_qorder = 0
                    for result in results:
                        if 'quality' in result:
                            quality = result['quality']
                        else:
                            match = re.search(r'\((\d+p)\)', result['title'])
                            if match:
                                quality = scraper_utils.height_get_quality(match.group(1))
                            else:
                                match = re.search(r'\[(.*)\]$', result['title'])
                                q_str = match.group(1) if match else ''
                                quality = scraper_utils.blog_get_quality(video, q_str, '')
                                
                        logger.log(f'result: |{result}|{quality}|{Q_ORDER[quality]}|', log_utils.LOGDEBUG)
                        if Q_ORDER[quality] > best_qorder:
                            logger.log(f'Setting best as: |{result}|{quality}|{Q_ORDER[quality]}|', log_utils.LOGDEBUG)
                            best_result = result
                            best_qorder = Q_ORDER[quality]

                url = best_result['url']
                self.db_connection().set_related_url(video.video_type, video.title, video.year, self.get_name(), url, video.season, video.episode)
        return url

    def _get_direct_hostname(self, link):
        host = urllib_parse.urlparse(link).hostname
        if host and any(h in host for h in ['google', 'orion', 'blogspot']):
            return 'gvideo'
        else:
            return self.get_name()
    
    def _parse_google(self, link):
        sources = []
        html = self._http_get(link, cache_limit=.25)
        match = re.search(r'pid=([^&]+)', link)
        if match:
            vid_id = match.group(1)
            sources = self.__parse_gplus(vid_id, html, link)
        else:
            if 'drive.google' in link or 'docs.google' in link:
                sources = self._parse_gdocs(link)
            if 'picasaweb' in link:
                i = link.rfind('#')
                if i > -1:
                    link_id = link[i + 1:]
                else:
                    link_id = ''
                match = re.search(r'feedPreload:\s*(.*}]}})},', html, re.DOTALL)
                if match:
                    js = scraper_utils.parse_json(match.group(1), link)
                    for item in js['feed']['entry']:
                        if not link_id or item['gphoto$id'] == link_id:
                            for media in item['media']['content']:
                                if media['type'].startswith('video'):
                                    sources.append(media['url'].replace('%3D', '='))
                else:
                    match = re.search(r'preload\'?:\s*(.*}})},', html, re.DOTALL)
                    if match:
                        js = scraper_utils.parse_json(match.group(1), link)
                        for media in js['feed']['media']['content']:
                            if media['type'].startswith('video'):
                                sources.append(media['url'].replace('%3D', '='))

        sources = list(set(sources))
        return sources

    def __parse_gplus(self, vid_id, html, link=''):
        sources = []
        match = re.search(r'return\s+(\[\[.*?)\s*}}', html, re.DOTALL)
        if match:
            try:
                js = scraper_utils.parse_json(match.group(1), link)
                for top_item in js:
                    if isinstance(top_item, list):
                        for item in top_item:
                            if isinstance(item, list):
                                for item2 in item:
                                    if isinstance(item2, list):
                                        for item3 in item2:
                                            if item3 == vid_id:
                                                sources = self.__extract_video(item2)
            except Exception as e:
                log_utils.log(f'Google Plus Parse failure: {link} - {e}', log_utils.LOGWARNING)
        return sources

    def __extract_video(self, item):
        sources = []
        for e in item:
            if isinstance(e, dict):
                for key in e:
                    for item2 in e[key]:
                        if isinstance(item2, list):
                            for item3 in item2:
                                if isinstance(item3, list):
                                    for item4 in item3:
                                        if isinstance(item4, str):
                                            s = urllib_parse.unquote(item4).replace('\\0026', '&').replace('\\003D', '=')
                                            for match in re.finditer(r'url=([^&]+)', s):
                                                sources.append(match.group(1))
        return sources
        
    def _parse_gdocs(self, link):
        urls = []
        html = self._http_get(link, cache_limit=.5)
        for match in re.finditer(r'\[\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\]', html):
            key, value = match.groups()
            if key == 'fmt_stream_map':
                items = value.split(',')
                for item in items:
                    _source_fmt, source_url = item.split('|')
                    source_url = source_url.replace('\\u003d', '=').replace('\\u0026', '&')
                    source_url = urllib_parse.unquote(source_url)
                    source_url += f'|Cookie={self._get_stream_cookies()}'
                    urls.append(source_url)
                    
        return urls

    def _get_cookies(self):
        cj = self._set_cookies(self.base_url, {})
        cookies = {cookie.name: cookie.value for cookie in cj}
        return cookies
        
    def _get_stream_cookies(self):
        cookies = [f'{key}={value}' for key, value in self._get_cookies().items()]
        return urllib_parse.quote('; '.join(cookies))

    def db_connection(self):
        if self.__db_connection is None:
            self.__db_connection = DB_Connection()
        return self.__db_connection
        
    def _parse_sources_list(self, html):
        sources = {}
        match = re.search(r'sources\s*:\s*\[(.*?)\]', html, re.DOTALL)
        if not match:
            match = re.search(r'sources\s*:\s*\{(.*?)\}', html, re.DOTALL)
            
        if match:
            for match in re.finditer(r'''['"]?file['"]?\s*:\s*['"]([^'"]+)['"][^}]*['"]?label['"]?\s*:\s*['"]([^'"]*)''', match.group(1), re.DOTALL):
                stream_url, label = match.groups()
                stream_url = stream_url.replace('\/', '/')
                if self._get_direct_hostname(stream_url) == 'gvideo':
                    sources[stream_url] = {'quality': scraper_utils.gv_get_quality(stream_url), 'direct': True}
                elif re.search(r'\d+p?', label, re.I):
                    sources[stream_url] = {'quality': scraper_utils.height_get_quality(label), 'direct': True}
                else:
                    sources[stream_url] = {'quality': label, 'direct': True}
        return sources

    def _get_files(self, url, headers=None, cache_limit=.5):
        sources = []
        for row in self._parse_directory(self._http_get(url, headers=headers, cache_limit=cache_limit)):
            source_url = scraper_utils.urljoin(url, row['link'])
            if row['directory'] and not row['link'].startswith('..'):
                sources += self._get_files(source_url, headers={'Referer': url}, cache_limit=cache_limit)
            else:
                row['url'] = source_url
                sources.append(row)
        return sources
    
    def _parse_directory(self, html):
        rows = []
        for match in re.finditer(self.row_pattern, html):
            row = match.groupdict()
            if row['title'].endswith('/'):
                row['title'] = row['title'][:-1]
            row['directory'] = True if row['link'].endswith('/') else False
            if row['size'] == '-':
                row['size'] = None
            rows.append(row)
        return rows