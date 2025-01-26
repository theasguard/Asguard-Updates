"""
    Asguard Kodi Addon Aniwatch Scraper
    Copyright (C) 2024

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

import urllib.parse
import requests
from bs4 import BeautifulSoup
import re, kodi
from asguard_lib.cf_captcha import NoRedirection
import log_utils
import cfscrape
from asguard_lib import scraper_utils, control, cloudflare, cf_captcha
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES, QUALITIES, Q_ORDER
from asguard_lib.utils2 import i18n, ungz
import resolveurl
from . import scraper

logger = log_utils.Logger.get_logger()

BASE_URL = 'https://aniwatchtv.to'
LOCAL_UA = 'Asguard for Kodi/%s' % (kodi.get_version())
FLARESOLVERR_URL = 'http://localhost:8191/v1'
MAX_RESPONSE = 1024 * 1024 * 5
CF_CAPCHA_ENABLED = kodi.get_setting('cf_captcha') == 'true'

class Scraper(scraper.Scraper):
    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name())) or BASE_URL
        self.scraper = cfscrape.create_scraper()
        self.headers = {
            'User-Agent': scraper_utils.get_ua(),
            'Referer': self.base_url
        }

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Aniwatch'

    def search(self, video_type, title, year, season=''):
        search_url = urllib.parse.urljoin(self.base_url, '/search')
        params = {'keyword': title}
        results = []

        try:
            html = self._http_get(search_url, params=params)
            soup = BeautifulSoup(html, 'html.parser')
            
            for item in soup.select('div.flw-item'):
                anchor = item.select_one('h2.film-name a')
                if not anchor: continue
                
                result_title = anchor.get_text(strip=True)
                url = urllib.parse.urljoin(self.base_url, anchor['href'])
                
                year_span = item.select_one('.fdi-item:first-child')
                result_year = int(year_span.text) if year_span and year_span.text.isdigit() else None
                
                if year and result_year and abs(int(year) - result_year) > 2:
                    continue
                
                results.append({
                    'title': result_title,
                    'url': url,
                    'year': result_year
                })
                
        except Exception as e:
            logger.log_error(f'Search failed: {str(e)}')
        
        return results

    def get_episodes(self, show_url):
        episodes = []
        try:
            html = self._http_get(show_url)
            soup = BeautifulSoup(html, 'html.parser')
            
            for ep in soup.select('div.ss-list a'):
                ep_number = ep.get_text(strip=True).split()[-1]
                if ep_number.isdigit():
                    episodes.append({
                        'number': int(ep_number),
                        'url': urllib.parse.urljoin(self.base_url, ep['href'])
                    })
                    
        except Exception as e:
            logger.log_error(f'Episode fetch failed: {str(e)}')
            
        return sorted(episodes, key=lambda x: x['number'])

    def get_sources(self, video):
        hosters = []
        try:
            html = self._http_get(video.url)
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract embedded iframe
            iframe = soup.find('iframe', {'id': 'main-iframe'})
            if iframe and iframe.get('src'):
                embed_url = urllib.parse.urljoin(self.base_url, iframe['src'])
                hosters.append({
                    'quality': scraper_utils.height_get_quality(1080),
                    'url': embed_url,
                    'host': 'Aniwatch',
                    'direct': False
                })
            
            # Extract direct sources
            for script in soup.find_all('script'):
                if 'sources' in script.text:
                    matches = re.findall(r'file:"(.*?)"', script.text)
                    for url in matches:
                        if url.endswith('.m3u8'):
                            hosters.append({
                                'quality': scraper_utils.height_get_quality(720),
                                'url': url,
                                'host': 'Direct',
                                'direct': True
                            })
                            
        except Exception as e:
            logger.log_error(f'Source extraction failed: {str(e)}')
            
        return hosters

    def _http_get(self, url, params=None, data=None, retry=True):
        try:
            if CF_CAPCHA_ENABLED:
                with NoRedirection():
                    response = self.scraper.get(url, params=params, data=data, 
                                              headers=self.headers, 
                                              timeout=self.timeout)
                    if response.status_code in [403, 503]:
                        cloudflare.solve(response.url, FLARESOLVERR_URL)
                        response = self.scraper.get(url, params=params, data=data, 
                                                  headers=self.headers, 
                                                  timeout=self.timeout)
            else:
                response = self.scraper.get(url, params=params, data=data, 
                                          headers=self.headers, 
                                          timeout=self.timeout)
                
            response.raise_for_status()
            return response.content.decode('utf-8')
            
        except Exception as e:
            logger.log_error(f'HTTP GET failed: {str(e)}')
            return ''

    @classmethod
    def get_settings(cls):
        settings = super().get_settings()
        name = cls.get_name()
        settings.append(f'         <setting id="{name}-quality" label="     {i18n("preferred_quality")}" type="enum" values="High|Medium|Low" default="0" visible="true"/>')
        return settings
