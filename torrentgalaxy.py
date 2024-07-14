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
import logging
import re
import requests
import kodi
from asguard_lib import cfscrape
import urllib.parse
from bs4 import BeautifulSoup
from asguard_lib.utils2 import i18n
import log_utils
from asguard_lib import scraper_utils, client
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
from . import scraper
from . import proxy

try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)

logging.basicConfig(level=logging.DEBUG)
logger = log_utils.Logger.get_logger()
BASE_URL = 'https://tgx.rs'
SEARCH_URL = '/torrents.php?search=%s&sort=seeders&order=desc'
QUALITY_MAP = {'1080p': QUALITIES.HD1080, '720p': QUALITIES.HD720, '480p': QUALITIES.HIGH, '360p': QUALITIES.MEDIUM}

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')
        self.result_limit = kodi.get_setting(f'{self.get_name()}-result_limit')
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:102.0) Gecko/20100101 Firefox/102.0'}
        self.scraper = cfscrape.create_scraper()

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'TorrentGalaxy'

    @classmethod
    def has_proxy(cls):
        return True

    def resolve_link(self, link):
        return link

    def get_sources(self, video):
        hosters = []
        query = self._build_query(video)
        logger.log('Searching for: %s' % query, log_utils.LOGDEBUG)
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL % urllib.parse.quote_plus(query))
        logger.log('Search URL: %s' % search_url, log_utils.LOGDEBUG)
        html = self._http_get(search_url, require_debrid=True)
        logger.log('HTML: %s' % html, log_utils.LOGDEBUG)
        
        if "GALAXY CHECKPOINT" in html or "TGx:Checkpoint" in html:
            logger.log('Encountered Checkpoint, attempting to bypass...', log_utils.LOGDEBUG)
            response = self.scraper.get(search_url, headers=self.headers, timeout=10)
            html = response.text
            logger.log('HTML after bypass: %s' % html, log_utils.LOGDEBUG)

        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all('div', class_='tgxtablerow txlight')
        if not rows: return hosters
        logger.log('Rows: %s' % rows, log_utils.LOGDEBUG)
        
        for row in rows:
            try:
                name_tag = row.find('a', class_='txlight')
                logger.log('Name tag: %s' % name_tag, log_utils.LOGDEBUG)
                name = name_tag.get('title') if name_tag else 'N/A'
                magnet_tag = row.find('a', href=True, title='Magnet link')
                magnet_link = magnet_tag['href'] if magnet_tag and magnet_tag['href'].startswith('magnet:') else 'N/A'
                size_tag = row.find('span', class_='badge badge-secondary')
                size = size_tag.text if size_tag else 'N/A'

                quality = scraper_utils.get_tor_quality(name)
                info = self.get_info(name)
                hoster = {'multi-part': False, 'url': magnet_link, 'title': name, 'info': info, 'class': self, 'host': 'magnet', 'quality': quality, 'direct': False, 'debridonly': True, 'size': size}
                hosters.append(hoster)

            except AttributeError as e:
                logger.log(f'Error parsing torrent: {e}', log_utils.LOGWARNING)
                continue

        return hosters

    def _build_query(self, video):
        query = video.title
        if video.video_type == VIDEO_TYPES.EPISODE:
            query += f' S{int(video.season):02d}E{int(video.episode):02d}'
        elif video.video_type == VIDEO_TYPES.MOVIE:
            query += f' {video.year}'
        return query


    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        name = cls.get_name()
        settings.append(f'         <setting id="{name}-result_limit" label="     {i18n("result_limit")}" type="slider" default="10" range="10,100" option="int" visible="true"/>')
        return settings

    def get_info(self, title):
        info = []
        if 'x264' in title:
            info.append('x264')
        if 'x265' in title or 'HEVC' in title:
            info.append('x265')
        if 'HDR' in title:
            info.append('HDR')
        return ', '.join(info)
    
def _http_get(self, url, require_debrid=False):
    if require_debrid and not self.debrid_resolvers:
        logger.log('%s requires debrid: %s' % (self.__module__, self.debrid_resolvers), log_utils.LOGDEBUG)
        return ''

    try:
        session = requests.Session()
        session.headers.update(self.headers)
        response = session.get(url, timeout=self.timeout)
        response.raise_for_status()  # Check for HTTP request errors

        # Update session cookies if necessary
        if 'PHPSESSID' in session.cookies:
            session.cookies.set('PHPSESSID', session.cookies['PHPSESSID'], domain='torrentgalaxy.to')

        html = response.text
        logger.log('HTML after request: %s' % html, log_utils.LOGDEBUG)
        return html
    except requests.exceptions.RequestException as e:
        logger.log('HTTP request error: %s - %s' % (str(e), url), log_utils.LOGWARNING)
        return ''