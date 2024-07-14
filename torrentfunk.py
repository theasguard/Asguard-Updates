"""
    Asguard Kodi Addon
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
import urllib.parse
import urllib.request
import urllib.error
from bs4 import BeautifulSoup, SoupStrainer
import resolveurl
import log_utils
from asguard_lib import scraper_utils, control
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
from asguard_lib.utils2 import i18n
from . import scraper
import concurrent.futures

logging.basicConfig(level=logging.DEBUG)

logger = log_utils.Logger.get_logger()
BASE_URL = "https://www.torrentfunk.com"
SEARCH_URL_TV = '/television/torrents/%s.html?v=on&smi=0&sma=0&i=75&sort=size&o=desc'
SEARCH_URL_MOVIE = '/movie/torrents/%s.html?v=on&smi=0&sma=0&i=75&sort=size&o=desc'
QUALITY_MAP = {'1080p': QUALITIES.HD1080, '720p': QUALITIES.HD720, '480p': QUALITIES.HIGH, '360p': QUALITIES.MEDIUM}

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = control.getSetting(f'{self.get_name()}-base_url') or BASE_URL
        self.result_limit = control.getSetting(f'{self.get_name()}-result_limit')
        self.min_seeders = 0

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'TorrentFunk'

    def get_sources(self, video):
        hosters = []
        query = self._build_query(video)
        if video.video_type == VIDEO_TYPES.MOVIE:
            search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL_MOVIE % urllib.parse.quote_plus(query))
        else:
            search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL_TV % urllib.parse.quote_plus(query))

        html = self._http_get(search_url, require_debrid=True)
        if not html:
            return hosters

        soup = BeautifulSoup(html, "html.parser", parse_only=SoupStrainer('table', attrs={'class': 'tmain'}))
        items = []
        for entry in soup.find_all('a', href=True):
            try:
                name = entry.text.strip()
                torrent_page = entry.get('href')
                torrent_page_url = urllib.parse.urljoin(self.base_url, torrent_page)
                items.append((name, torrent_page_url))
            except Exception as e:
                logging.error("Error parsing entry: %s", str(e))
                continue

        def fetch_source(item):
            try:
                name, torrent_page_url = item
                torrent_page_html = self._http_get(torrent_page_url)
                if not torrent_page_html:
                    return

                magnet_match = re.search(r'href\s*=\s*["\'](magnet:.+?)["\']', torrent_page_html, re.I)
                if not magnet_match:
                    return
                magnet = magnet_match.group(1)

                size_match = re.search(r'Size:.*?>((?:\d+\,\d+\.\d+|\d+\.\d+|\d+\,\d+|\d+)\s*(?:GB|GiB|Gb|MB|MiB|Mb))', torrent_page_html)
                size = size_match.group(1) if size_match else 'NA'

                seeders_match = re.search(r'Seeders:.*?>([0-9]+|[0-9]+,[0-9]+)</', torrent_page_html, re.I)
                seeders = int(seeders_match.group(1).replace(',', '')) if seeders_match else 0

                if self.min_seeders > seeders:
                    return

                quality = scraper_utils.get_tor_quality(name)
                host = scraper_utils.get_direct_hostname(self, magnet)
                label = f"{name} | {quality} | {size}"
                hosters.append({
                    'name': name,
                    'label': label,
                    'multi-part': False,
                    'class': self,
                    'url': magnet,
                    'size': size,
                    'seeders': seeders,
                    'quality': quality,
                    'host': 'magnet',
                    'direct': False,
                    'debridonly': True
                })
            except Exception as e:
                logging.error("Error fetching source: %s", str(e))

        with concurrent.futures.ThreadPoolExecutor() as executor:
            executor.map(fetch_source, items)

        return hosters

    def _build_query(self, video):
        query = video.title
        query = scraper_utils.cleanse_title(query)
        if video.video_type == VIDEO_TYPES.TVSHOW:
            query += f' S{int(video.season):02d}E{int(video.episode):02d}'
        elif video.video_type == VIDEO_TYPES.MOVIE:
            query += f' {video.year}'
        query = query.replace(' ', '+').replace('+-', '-')
        return query

    def _filter_sources(self, hosters, video):
        filtered_sources = []
        for source in hosters:
            if video.video_type == VIDEO_TYPES.TVSHOW:
                if not self._match_episode(source['name'], video.season, video.episode):
                    continue
            filtered_sources.append(source)
        return filtered_sources

    def _match_episode(self, title, season, episode):
        regex_ep = re.compile(r'\bS(\d+)E(\d+)\b')
        match = regex_ep.search(title)
        if match:
            season_num = int(match.group(1))
            episode_num = int(match.group(2))
            if season_num == int(season) and episode_num == int(episode):
                return True
        return False

    def _http_get(self, url, data=None, retry=True, allow_redirect=True, cache_limit=8, require_debrid=True):
        if require_debrid:
            if Scraper.debrid_resolvers is None:
                Scraper.debrid_resolvers = [resolver for resolver in resolveurl.relevant_resolvers() if resolver.isUniversal()]
            if not Scraper.debrid_resolvers:
                logger.log('%s requires debrid: %s' % (self.__module__, Scraper.debrid_resolvers), log_utils.LOGDEBUG)
                return ''
        try:
            headers = {'User-Agent': scraper_utils.get_ua()}
            req = urllib.request.Request(url, data=data, headers=headers)
            logging.debug("HTTP request: %s", req)
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return response.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            logger.log(f'HTTP Error: {e.code} - {url}', log_utils.LOGWARNING)
        except urllib.error.URLError as e:
            logger.log(f'URL Error: {e.reason} - {url}', log_utils.LOGWARNING)
        return ''

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        name = cls.get_name()
        settings.append(f'         <setting id="{name}-result_limit" label="     {i18n("result_limit")}" type="slider" default="10" range="10,100" option="int" visible="true"/>')
        return settings
