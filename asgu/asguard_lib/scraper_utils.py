"""
    Asguard Addon
    Copyright (C) 2016 Mr Blamo

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
import base64
import hashlib
import re
import random
import sys
import time
import json
import os.path
import string
import kodi
import log_utils
import dom_parser2
import xbmcgui
import six
from six.moves import urllib_parse, urllib_request, urllib_error
from . import client
from urllib.parse import urlparse, urlunparse, quote_plus, unquote, parse_qs
from asguard_lib import directstream
from asguard_lib import pyaes
from asguard_lib import utils2
from asguard_lib.constants import *  # @UnusedWildImport

logger = log_utils.Logger.get_logger(__name__)
# logger.disable()

cleanse_title = utils2.cleanse_title
to_datetime = utils2.to_datetime
normalize_title = utils2.normalize_title
CAPTCHA_BASE_URL = 'http://www.google.com/recaptcha/api'

def disable_sub_check(settings):
    for i in reversed(range(len(settings))):
        if 'sub_check' in settings[i]:
            settings[i] = settings[i].replace('default="true"', 'default="false"')
    return settings

def get_ua():
    try:
        last_gen = int(kodi.get_setting('last_ua_create'))
    except:
        last_gen = 0
    if not kodi.get_setting('current_ua') or last_gen < (time.time() - (7 * 24 * 60 * 60)):
        index = random.randrange(len(RAND_UAS))
        versions = {'win_ver': random.choice(WIN_VERS), 'feature': random.choice(FEATURES), 'br_ver': random.choice(BR_VERS[index])}
        user_agent = RAND_UAS[index].format(**versions)
        logger.log('Creating New User Agent: %s' % (user_agent), log_utils.LOGDEBUG)
        kodi.set_setting('current_ua', user_agent)
        kodi.set_setting('last_ua_create', str(int(time.time())))
    else:
        user_agent = kodi.get_setting('current_ua')
    return user_agent

def cookies_as_str(cj):
    s = ''
    c = cj._cookies
    for domain in c:
        s += '{%s: ' % (domain)
        for path in c[domain]:
            s += '{%s: ' % (path)
            for cookie in c[domain][path]:
                s += '{%s=%s}' % (cookie, c[domain][path][cookie].value)
            s += '}'
        s += '} '
    return s
                
# TODO: Test with CJ
def fix_bad_cookies(cookies):
    for domain in cookies:
        for path in cookies[domain]:
            for key in cookies[domain][path]:
                cookie = cookies[domain][path][key]
                if cookie.expires > sys.maxsize:
                    logger.log('Fixing cookie expiration for %s: was: %s now: %s' % (key, cookie.expires, sys.maxsize), log_utils.LOGDEBUG)
                    cookie.expires = sys.maxsize
    return cookies

def force_title(video):
    trakt_str = kodi.get_setting('force_title_match')
    trakt_list = trakt_str.split('|') if trakt_str else []
    return str(video.trakt_id) in trakt_list

def blog_get_quality(video, q_str, host):
    q_str = q_str.replace(video.title, '').replace(str(video.year), '').upper()
    post_quality = None
    for key in [item[0] for item in sorted(Q_ORDER.items(), key=lambda x: x[1])]:
        if any(q in q_str for q in BLOG_Q_MAP[key]):
            post_quality = key
    return get_quality(video, host, post_quality)

def get_quality(video, host, base_quality=None):
    if host is None:
        host = ''
    host = host.lower()
    # Assume movies are low quality, tv shows are high quality
    if base_quality is None:
        if video.video_type == VIDEO_TYPES.MOVIE:
            quality = QUALITIES.LOW
        else:
            quality = QUALITIES.HIGH
    else:
        quality = base_quality

    host_quality = None
    if host:
        for key in HOST_Q:
            if any(hostname in host for hostname in HOST_Q[key]):
                host_quality = key
                break

    # logger.log('q_str: %s, host: %s, post q: %s, host q: %s' % (q_str, host, post_quality, host_quality), log_utils.LOGDEBUG)
    if host_quality is not None and Q_ORDER[host_quality] < Q_ORDER[quality]:
        quality = host_quality

    return quality

def width_get_quality(width):
    try:
        width = int(width)
    except:
        width = 320
    if width > 2160:
        quality = QUALITIES.HD4K
    elif width > 1280:
        quality = QUALITIES.HD1080
    elif width > 854:
        quality = QUALITIES.HD720
    elif width > 640:
        quality = QUALITIES.HIGH
    elif width > 320:
        quality = QUALITIES.MEDIUM
    else:
        quality = QUALITIES.LOW
    return quality

def height_get_quality(height):
    if str(height)[-1] in ['p', 'P']:
        height = str(height)[:-1]
        
    try:
        height = int(height)
    except:
        height = 200
    if height >= 1000:
        quality = QUALITIES.HD4K
    elif height >= 800:
        quality = QUALITIES.HD1080
    elif height > 480:
        quality = QUALITIES.HD720
    elif height >= 400:
        quality = QUALITIES.HIGH
    elif height > 200:
        quality = QUALITIES.MEDIUM
    else:
        quality = QUALITIES.LOW
    return quality

def gv_get_quality(stream_url):
    stream_url = unquote(stream_url)
    if 'itag=18' in stream_url or '=m18' in stream_url or '/m18' in stream_url:
        return QUALITIES.MEDIUM
    elif 'itag=22' in stream_url or '=m22' in stream_url or '/m22' in stream_url:
        return QUALITIES.HD720
    elif 'itag=15' in stream_url or '=m15' in stream_url or '/m15' in stream_url:
        return QUALITIES.HD720
    elif 'itag=45' in stream_url or '=m45' in stream_url or '/m45' in stream_url:
        return QUALITIES.HD720
    elif 'itag=34' in stream_url or '=m34' in stream_url or '/m34' in stream_url:
        return QUALITIES.MEDIUM
    elif 'itag=35' in stream_url or '=m35' in stream_url or '/m35' in stream_url:
        return QUALITIES.HIGH
    elif 'itag=59' in stream_url or '=m59' in stream_url or '/m59' in stream_url:
        return QUALITIES.HIGH
    elif 'itag=44' in stream_url or '=m44' in stream_url or '/m44' in stream_url:
        return QUALITIES.HIGH
    elif 'itag=37' in stream_url or '=m37' in stream_url or '/m37' in stream_url:
        return QUALITIES.HD1080
    elif 'itag=38' in stream_url or '=m38' in stream_url or '/m38' in stream_url:
        return QUALITIES.HD1080
    elif 'itag=46' in stream_url or '=m46' in stream_url or '/m46' in stream_url:
        return QUALITIES.HD1080
    elif 'itag=37' in stream_url or '=m37' in stream_url or '/m37' in stream_url:
        return QUALITIES.HD4K
    elif 'itag=46' in stream_url or '=m46' in stream_url or '/m46' in stream_url:
        return QUALITIES.HD4K
    elif 'itag=96' in stream_url or '=m96' in stream_url or '/m96' in stream_url:
        return QUALITIES.HD4K
    elif 'itag=43' in stream_url or '=m43' in stream_url or '/m43' in stream_url:
        return QUALITIES.MEDIUM
    else:
        return QUALITIES.HIGH

def label_to_quality(label):
    try:
        label = int(re.search(r'(\d+)', label).group(1))
    except:
        label = 0

    if label >= 2160:
        return '4K'
    elif label >= 1440:
        return '1440p'
    elif label >= 1080:
        return '1080p'
    elif 720 <= label < 1080:
        return '720p'
    elif label < 720:
        return 'SD'
    else:
        return 'SD'

def getFileType(url):
    try:
        url = url.lower()
    except:
        url = str(url)
    type = ''
    
    if 'bluray' in url: type += ' BLURAY /'
    if '.web-dl' in url: type += ' WEB-DL /'
    if '.web.' in url: type += ' WEB-DL /'
    if 'hdrip' in url: type += ' HDRip /'
    if 'bd-r' in url: type += ' BD-R /'
    if 'bd-rip' in url: type += ' BD-RIP /'
    if 'bd.r' in url: type += ' BD-R /'
    if 'bd.rip' in url: type += ' BD-RIP /'
    if 'bdr' in url: type += ' BD-R /'
    if 'bdrip' in url: type += ' BD-RIP /'
    if 'atmos' in url: type += ' ATMOS /'
    if 'truehd' in url: type += ' TRUEHD /'
    if '.dd' in url: type += ' DolbyDigital /'
    if '5.1' in url: type += ' 5.1 /'
    if '.xvid' in url: type += ' XVID /'
    if 'mkv' in url: type += ' MKV /'
    if '.mp4' in url: type += ' MP4 /'
    if '.avi' in url: type += ' AVI /'
    if 'ac3' in url: type += ' AC3 /'
    if 'h.264' in url: type += ' H.264 /'
    if '.x264' in url: type += ' x264 /'
    if '.x265' in url: type += ' x265 /'
    if 'subs' in url: 
        if type != '': type += ' - WITH SUBS'
        else: type = 'SUBS'
    type = type.rstrip('/')
    return type

def check_sd_url(release_link):

    try:
        release_link = release_link.lower()
        if '4k' in release_link:
            quality = '4K'
        elif '1080' in release_link:
            quality = '1080p'
        elif '720' in release_link:
            quality = '720p'
        elif '.hd.' in release_link:
            quality = '720p'
        elif any(i in ['dvdscr', 'r5', 'r6'] for i in release_link):
            quality = 'SCR'
        elif any(i in ['camrip', 'tsrip', 'hdcam', 'hdts', 'dvdcam', 'dvdts', 'cam', 'telesync', 'ts'] for i in release_link):
            quality = 'CAM'
        else:
            quality = 'SD'
        return quality
    except:
        return 'SD'

def get_release_quality(release_name, release_link=None):
    if release_name is None:
        return

    try:
        release_name = release_name.encode('utf-8')
    except:
        pass

    try:
        quality = None
        
        release_name = release_name.upper()
        fmt = re.sub(r'(.+)(\.|\(|\[|\s)(\d{4}|S\d*E\d*|S\d*)(\.|\)|\]|\s)', '', release_name)
        fmt = re.split(r'\.|\(|\)|\[|\]|\s|-', fmt)
        fmt = [i.lower() for i in fmt]
        if '4k' in fmt:
            quality = '4K'
        elif '1080p' in fmt:
            quality = '1080p'
        elif '720p' in fmt:
            quality = '720p'
        elif 'brrip' in fmt:
            quality = '720p'
        elif any(i in ['dvdscr', 'r5', 'r6'] for i in fmt):
            quality = 'SCR'
        elif any(i in ['camrip', 'tsrip', 'hdcam', 'hdts', 'dvdcam', 'dvdts', 'cam', 'telesync', 'ts'] for i in fmt):
            quality = 'CAM'

        if not quality:
            if release_link:
                release_link = release_link.lower()
                try:
                    release_link = release_link.encode('utf-8')
                except:
                    pass
                if '4k' in release_link:
                    quality = '4K'
                elif '1080' in release_link:
                    quality = '1080p'
                elif '720' in release_link:
                    quality = '720p'
                elif '.hd' in release_link:
                    quality = 'SD'
                else:
                    if any(i in ['dvdscr', 'r5', 'r6'] for i in release_link):
                        quality = 'SCR'
                    elif any(i in ['camrip', 'tsrip', 'hdcam', 'hdts', 'dvdcam', 'dvdts', 'cam', 'telesync', 'ts'] for i in release_link):
                        quality = 'CAM'
                    else:
                        quality = 'SD'
            else:
                quality = 'SD'
        info = []
        if '3d' in fmt or '.3D.' in release_name:
            info.append('3D')
        if any(i in ['hevc', 'h265', 'x265'] for i in fmt):
            info.append('HEVC')

        return quality, info
    except:
        return 'SD', []

def strip_domain(url):
    try:
        if url.lower().startswith('http') or url.startswith('/'):
            url = re.findall(r'(?://.+?|)(/.+)', url)[0]
        url = client.replaceHTMLCodes(url)
        url = url.encode('utf-8')
        return url
    except:
        return

def is_host_valid(url, domains):
    try:
        host = __top_domain(url)
        hosts = [domain.lower() for domain in domains if host and host in domain.lower()]

        if hosts and '.' not in host:
            host = hosts[0]
        if hosts and any([h for h in ['google', 'orion', 'blogspot'] if h in host]):
            host = 'gvideo'
        if hosts and any([h for h in ['akamaized', 'ocloud'] if h in host]):
            host = 'CDN'
        return any(hosts), host
    except:
        return False, ''

def __top_domain(url):
    elements = urlparse(url)
    domain = elements.netloc or elements.path
    domain = domain.split('@')[-1].split(':')[0]
    regex = r"(?:www\.)?([\w\-]*\.[\w\-]{2,3}(?:\.[\w\-]{2,3})?)$"
    res = re.search(regex, domain)
    if res:
        domain = res.group(1)
    domain = domain.lower()
    return domain

def aliases_to_array(aliases, filter=None):
    try:
        if not filter:
            filter = []
        if isinstance(filter, str):
            filter = [filter]

        return [x.get('title') for x in aliases if not filter or x.get('country') in filter]
    except Exception as e:
        log_utils.log(f"Error in aliases_to_array: {e}", log_utils.LOGWARNING)
        return []

def append_headers(headers):
    return '|%s' % '&'.join(['%s=%s' % (key, quote_plus(headers[key])) for key in headers])

def get_size(url):
    try:
        size = client.request(url, output='file_size')
        if size == '0':
            size = False
        size = convert_size(size)
        return size
    except Exception as e:
        log_utils.log(f"Error in get_size: {e}", log_utils.LOGWARNING)
        return False

def convert_size(size_bytes):
    import math
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    if size_name[i] == 'B' or size_name[i] == 'KB':
        return None
    return "%s %s" % (s, size_name[i])

def check_directstreams(url, hoster='', quality='SD'):
    urls = []
    host = hoster

    if 'google' in url or any(x in url for x in ['youtube.', 'docid=']):
        urls = directstream.google(url)
        if not urls:
            tag = directstream.googletag(url)
            if tag:
                urls = [{'quality': tag[0]['quality'], 'url': url}]
        if urls:
            host = 'gvideo'
    elif 'ok.ru' in url:
        urls = directstream.odnoklassniki(url)
        if urls:
            host = 'vk'
    elif 'vk.com' in url:
        urls = directstream.vk(url)
        if urls:
            host = 'vk'
    elif any(x in url for x in ['akamaized', 'blogspot', 'ocloud.stream']):
        urls = [{'url': url}]
        if urls:
            host = 'CDN'
        
    direct = True if urls else False

    if not urls:
        urls = [{'quality': quality, 'url': url}]

    return urls, host, direct

# if salt is provided, it should be string
# ciphertext is base64 and passphrase is string
def evp_decode(cipher_text, passphrase, salt=None):
    cipher_text = base64.b64decode(cipher_text)
    if not salt:
        salt = cipher_text[8:16]
        cipher_text = cipher_text[16:]
    data = evpKDF(passphrase, salt)
    decrypter = pyaes.Decrypter(pyaes.AESModeOfOperationCBC(data['key'], data['iv']))
    plain_text = decrypter.feed(cipher_text)
    plain_text += decrypter.feed()
    return plain_text

def evpKDF(passwd, salt, key_size=8, iv_size=4, iterations=1, hash_algorithm="md5"):
    target_key_size = key_size + iv_size
    derived_bytes = b""
    number_of_derived_words = 0
    block = None
    hasher = hashlib.new(hash_algorithm)
    while number_of_derived_words < target_key_size:
        if block is not None:
            hasher.update(block)

        hasher.update(passwd.encode('utf-8'))
        hasher.update(salt)
        block = hasher.digest()
        hasher = hashlib.new(hash_algorithm)

        for _i in range(1, iterations):
            hasher.update(block)
            block = hasher.digest()
            hasher = hashlib.new(hash_algorithm)

        derived_bytes += block[0: min(len(block), (target_key_size - number_of_derived_words) * 4)]

        number_of_derived_words += len(block) // 4

    return {
        "key": derived_bytes[0: key_size * 4],
        "iv": derived_bytes[key_size * 4:]
    }

def get_sucuri_cookie(html):
    if 'sucuri_cloudproxy_js' in html:
        match = re.search("S\s*=\s*'([^']+)", html)
        if match:
            s = base64.b64decode(match.group(1))
            s = s.replace(b' ', b'')
            s = re.sub(b'String\.fromCharCode\(([^)]+)\)', rb'chr(\1)', s)
            s = re.sub(b'\.slice\((\d+),(\d+)\)', rb'[\1:\2]', s)
            s = re.sub(b'\.charAt\(([^)]+)\)', rb'[\1]', s)
            s = re.sub(b'\.substr\((\d+),(\d+)\)', rb'[\1:\1+\2]', s)
            s = re.sub(b';location.reload\(\);', b'', s)
            s = re.sub(rb'\n', b'', s)
            s = re.sub(rb'document\.cookie', b'cookie', s)
            try:
                cookie = ''
                exec(s)
                match = re.match('([^=]+)=(.*)', cookie)
                if match:
                    return {match.group(1): match.group(2)}
            except Exception as e:
                log_utils.log(f'Exception during sucuri js: {e}', log_utils.LOGWARNING)
    
    return {}
    
def gk_decrypt(name, key, cipher_link):
    try:
        key += (24 - len(key)) * '\0'
        decrypter = pyaes.Decrypter(pyaes.AESModeOfOperationECB(key))
        plain_text = decrypter.feed(bytes.fromhex(cipher_link))
        plain_text += decrypter.feed()
        plain_text = plain_text.split(b'\0', 1)[0]
    except Exception as e:
        log_utils.log(f'Exception ({e}) during {name} gk decrypt: cipher_link: {cipher_link}', log_utils.LOGWARNING)
        plain_text = b''

    return plain_text.decode('utf-8')

def parse_episode_link(link):
    episode = {'title': '', 'season': '-1', 'episode': '-1', 'airdate': '', 'height': '480', 'extra': '', 'dubbed': False}
    ep_patterns = [
        # episode with sxe or airdate and height
        r'(?P<title>.*?){delim}S(?P<season>\d+){delim}*E(?P<episode>\d+)(?:E\d+)*.*?{delim}(?P<height>\d+)p{delim}?(?P<extra>.*)',
        r'(?P<title>.*?){delim}(?P<season>\d+)x(?P<episode>\d+)(?:-\d+)*.*?{delim}(?P<height>\d+)p{delim}?(?P<extra>.*)',
        r'(?P<title>.*?){delim}SEASON{delim}*(?P<season>\d+){delim}*EPISODE{delim}*(?P<episode>\d+).*?{delim}(?P<height>\d+)p{delim}?(?P<extra>.*)',
        r'(?P<title>.*?){delim}\[S(?P<season>\d+)\]{delim}*\[E(?P<episode>\d+)(?:E\d+)*\].*?{delim}(?P<height>\d+)p{delim}?(?P<extra>.*)',
        r'(?P<title>.*?){delim}S(?P<season>\d+){delim}*EP(?P<episode>\d+)(?:EP\d+)*.*?{delim}(?P<height>\d+)p{delim}?(?P<extra>.*)',
        r'(?P<title>.*?){delim}\(?(?P<airdate>\d{{4}}{delim}\d{{1,2}}{delim}\d{{1,2}})\)?.*?{delim}(?P<height>\d+)p{delim}?(?P<extra>.*)',

        # episode with sxe or airdate not height
        r'(?P<title>.*?){delim}S(?P<season>\d+){delim}*E(?P<episode>\d+)(?:E\d+)*{delim}?(?P<extra>.*)',
        r'(?P<title>.*?){delim}(?P<season>\d+)x(?P<episode>\d+)(?:-\d+)*{delim}?(?P<extra>.*)',
        r'(?P<title>.*?){delim}SEASON{delim}*(?P<season>\d+){delim}*EPISODE{delim}*(?P<episode>\d+){delim}?(?P<extra>.*)',
        r'(?P<title>.*?){delim}\[S(?P<season>\d+)\]{delim}*\[E(?P<episode>\d+)(?:E\d+)*\]{delim}?(?P<extra>.*)',
        r'(?P<title>.*?){delim}S(?P<season>\d+){delim}*EP(?P<episode>\d+)(?:E\d+)*{delim}?(?P<extra>.*)',
        r'(?P<title>.*?){delim}\(?(?P<airdate>\d{{4}}{delim}\d{{1,2}}{delim}\d{{1,2}})\)?{delim}?(?P<extra>.*)',
        
        r'(?P<title>.*?){delim}(?P<height>\d{{3,}})p{delim}?(?P<extra>.*)',  # episode with height only
        r'(?P<title>.*)'  # title only
    ]
 
    return parse_link(link, episode, ep_patterns)

def parse_movie_link(link):
    movie = {'title': '', 'year': '', 'height': '480', 'extra': '', 'dubbed': False}
    movie_patterns = [
        r'(?P<title>.*?){delim}(?P<year>\d{{4}}){delim}.*?(?P<height>\d+)p{delim}(?P<extra>.*)',  # title, year, and quality present
        r'(?P<title>.*?){delim}(?P<year>\d{{4}}){delim}(?P<extra>.*)',  # title and year only
        r'(?P<title>.*?){delim}(?P<height>\d+)p{delim}(?P<extra>.*)',  # title and quality only
        r'(?P<title>.*)(?P<extra>\.[A-Z\d]{{3}}$)',  # title with extension
        r'(?P<title>.*)'  # title only
    ]
    return parse_link(link, movie, movie_patterns)

def parse_link(link, item, patterns):
    link = cleanse_title(unquote(link))
    file_name = link.split('/')[-1]
    for pattern in patterns:
        pattern = pattern.format(delim=DELIM)
        match = re.search(pattern, file_name, re.I)
        if match:
            match = {k: v for k, v in match.groupdict().items() if v is not None}
            item.update(match)
            break
    else:
        log_utils.log(f'No Regex Match: |{item}|{link}|', log_utils.LOGDEBUG)

    extra = item['extra'].upper()
    if 'X265' in extra or 'HEVC' in extra:
        item['format'] = 'x265'
    
    item['dubbed'] = True if 'DUBBED' in extra else False
    
    if 'airdate' in item and item['airdate']:
        pattern = '{delim}+'.format(delim=DELIM)
        item['airdate'] = re.sub(pattern, '-', item['airdate'])
        item['airdate'] = utils2.to_datetime(item['airdate'], "%Y-%m-%d").date()
        
    return item
    
def release_check(video, title, require_title=True):
    if isinstance(title, str): title = title.encode('utf-8')
    left_meta = {'title': video.title, 'height': '', 'extra': '', 'dubbed': False}
    if video.video_type == VIDEO_TYPES.MOVIE:
        left_meta.update({'year': video.year})
        right_meta = parse_movie_link(title)
    else:
        left_meta.update({'season': video.season, 'episode': video.episode, 'airdate': video.ep_airdate})
        right_meta = parse_episode_link(title)
        
    return meta_release_check(video.video_type, left_meta, right_meta, require_title)

def meta_release_check(video_type, left_meta, right_meta, require_title=True):
    norm_title = normalize_title(left_meta['title'])
    match_norm_title = normalize_title(right_meta['title'])
    title_match = not require_title or (norm_title and (match_norm_title in norm_title or norm_title in match_norm_title))
    try: year_match = not left_meta['year'] or not right_meta['year'] or left_meta['year'] == right_meta['year']
    except: year_match = True
    try: sxe_match = int(left_meta['season']) == int(right_meta['season']) and int(left_meta['episode']) == int(right_meta['episode'])
    except: sxe_match = False
    try: airdate_match = left_meta['airdate'] == right_meta['airdate']
    except: airdate_match = False
    
    matches = title_match and year_match
    if video_type == VIDEO_TYPES.EPISODE:
        matches = matches and (sxe_match or airdate_match)
        
    if not matches:
        log_utils.log(f'*{left_meta}*{right_meta}* - |{title_match}|{year_match}|{sxe_match}|{airdate_match}|', log_utils.LOGDEBUG)
    return matches

def pathify_url(url):
    url = url.replace('\/', '/')
    pieces = urlparse(url)
    if pieces.scheme:
        strip = pieces.scheme + ':'
    else:
        strip = ''
    strip += '//' + pieces.netloc
    url = url.replace(strip, '')
    if url.startswith('..'): url = url[2:]
    if not url.startswith('/'): url = '/' + url
    url = url.replace('/./', '/')
    url = url.replace('&amp;', '&')
    url = url.replace('//', '/')
    return url

def parse_json(html, url=''):
    if html:
        try:
            if not isinstance(html, str):
                if html.startswith(b'\xef\xbb\xbf'):
                    html = html[3:]
                elif html.startswith(b'\xfe\xff'):
                    html = html[2:]
                html = html.decode('utf-8')
                
            js_data = json.loads(html)
            if js_data is None:
                return {}
            else:
                return js_data
        except (ValueError, TypeError) as e:
            log_utils.log(f'Invalid JSON returned: {html}: {url} - {e}', log_utils.LOGWARNING)
            return {}
    else:
        log_utils.log(f'Empty JSON object: {html}: {url}', log_utils.LOGDEBUG)
        return {}

def format_size(num, suffix='B'):
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Y', suffix)

def to_bytes(num, unit):
    unit = unit.upper()
    if unit.endswith('B'): unit = unit[:-1]
    units = ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']
    try: mult = pow(1024, units.index(unit))
    except: mult = sys.maxsize
    return int(float(num) * mult)
    
def update_scraper(file_name, scraper_url, scraper_key):
    py_path = os.path.join(kodi.get_path(), 'scrapers', file_name)
    exists = os.path.exists(py_path)
    if not exists or (time.time() - os.path.getmtime(py_path)) > (8 * 60 * 60):
        new_py = utils2.get_and_decrypt(scraper_url, scraper_key)
        if new_py:
            if exists:
                with open(py_path, 'r') as f:
                    old_py = f.read()
            else:
                old_py = ''
            
            log_utils.log(f'{__file__} path: {py_path}, new_py: {bool(new_py)}, match: {new_py == old_py}', log_utils.LOGDEBUG)
            if old_py != new_py:
                with open(py_path, 'w') as f:
                    f.write(new_py)

def urljoin(base_url, url, scheme='http', replace_path=False):
    base_parts = urlparse(base_url)
    url_parts = urlparse(url)
    new_scheme = base_parts.scheme or url_parts.scheme or scheme
    new_netloc = url_parts.netloc or base_parts.netloc

    if replace_path:
        new_path = url_parts.path
    else:
        if url_parts.path:
            new_path = base_parts.path + '/' + url_parts.path
            new_path = new_path.replace('///', '/').replace('//', '/')
        else:
            new_path = base_parts.path

    if new_path == '/':
        new_path = ''

    new_params = base_parts.params if not url_parts.params else url_parts.params
    new_query = base_parts.query if not url_parts.query else url_parts.query
    new_fragment = base_parts.fragment if not url_parts.fragment else url_parts.fragment

    new_parts = (new_scheme, new_netloc, new_path, new_params, new_query, new_fragment)
    return urlunparse(new_parts)

def parse_params(params):
    result = {}
    params = params[1:-1]
    for element in params.split(','):
        key, value = element.split(':')
        key = re.sub('''['"]''', '', key.strip())
        value = re.sub('''['"]''', '', value.strip())
        result[key] = value
    return result

# if no default url has been set, then pick one and set it. If one has been set, use it
def set_default_url(Scraper):
    default_url = kodi.get_setting('%s-default_url' % (Scraper.get_name()))
    if not default_url:
        default_url = random.choice(Scraper.OPTIONS)
        kodi.set_setting('%s-default_url' % (Scraper.get_name()), default_url)
    Scraper.base_url = default_url
    return default_url

def extra_year(match_title_year):
    match_title_year = match_title_year.strip()
    match = re.search('(.*?)\s+\((\d{4})[^)]*\)', match_title_year, re.UNICODE)
    if match:
        match_title, match_year = match.groups()
    else:
        match = re.search('(.*?)\s+(\d{4})$', match_title_year, re.UNICODE)
        if match:
            match_title, match_year = match.groups()
        else:
            match_title = match_title_year
            match_year = ''
    return match_title, match_year

def get_token(hash_len=16):
    chars = string.digits + string.ascii_uppercase + string.ascii_lowercase
    base = hashlib.sha512(str(int(time.time()) // 60 // 60).encode('utf-8')).digest()
    return ''.join([chars[c % len(chars)] for c in base[:hash_len]])

def append_headers(headers):
    return '|%s' % '&'.join(['%s=%s' % (key, quote_plus(headers[key])) for key in headers])

def excluded_link(stream_url):
    return re.search(r'\.part\.?\d+', stream_url) or '.rar' in stream_url or 'sample' in stream_url or stream_url.endswith('.nfo')

def rshift(val, n):
    return (val % 0x100000000) >> n

def int32(x):
    x = 0xffffffff & x
    if x > 0x7fffffff:
        return int(-(~(x - 1) & 0xffffffff))
    else:
        return int(x)

# if salt is provided, it should be string
# ciphertext is base64 and passphrase is string
def evp_decode(cipher_text, passphrase, salt=None):
    cipher_text = base64.b64decode(cipher_text)
    if not salt:
        salt = cipher_text[8:16]
        cipher_text = cipher_text[16:]
    data = evpKDF(passphrase, salt)
    decrypter = pyaes.Decrypter(pyaes.AESModeOfOperationCBC(data['key'], data['iv']))
    plain_text = decrypter.feed(cipher_text)
    plain_text += decrypter.feed()
    return plain_text

def evpKDF(passwd, salt, key_size=8, iv_size=4, iterations=1, hash_algorithm="md5"):
    target_key_size = key_size + iv_size
    derived_bytes = b""
    number_of_derived_words = 0
    block = None
    hasher = hashlib.new(hash_algorithm)
    while number_of_derived_words < target_key_size:
        if block is not None:
            hasher.update(block)

        hasher.update(passwd.encode('utf-8'))
        hasher.update(salt.encode('utf-8'))
        block = hasher.digest()
        hasher = hashlib.new(hash_algorithm)

        for _i in range(1, iterations):
            hasher.update(block)
            block = hasher.digest()
            hasher = hashlib.new(hash_algorithm)

        derived_bytes += block[0: min(len(block), (target_key_size - number_of_derived_words) * 4)]

        number_of_derived_words += len(block) // 4

    return {
        "key": derived_bytes[0: key_size * 4],
        "iv": derived_bytes[key_size * 4:]
    }

def get_direct_hostname(scraper, link):
    host = urlparse(link).hostname
    if host and any(h in host for h in ['google', 'picasa', 'blogspot']):
        return 'gvideo'
    else:
        return scraper.get_name()

def parse_sources_list(scraper, html, key='sources', var=None, file_key=None):
    sources = {}
    match = re.search(r'''['"]?%s["']?\s*:\s*[\{\[](\s*)[\}\]]''' % (key), html, re.DOTALL)
    if not match:
        match = re.search(r'''['"]?%s["']?\s*:\s*\[(.*?)\}\s*,?\s*\]''' % (key), html, re.DOTALL)
        if not match:
            match = re.search(r'''['"]?%s["']?\s*:\s*\{(.*?)\}''' % (key), html, re.DOTALL)
            if not match and var is not None:
                match = re.search(r'''%s\s*=\s*[^\[]*\[\{(.*?)\}\]''' % (var), html, re.DOTALL)
                
    if match:
        fragment = match.group(1)
    elif var is not None:
        fragment = ''.join(re.findall(r"%s\.push\(([^)]+)" % (var), html, re.DOTALL))
    else:
        fragment = ''
    
    file_key = 'file' if file_key is None else file_key
    files = re.findall(r'''['"]?%s['"]?\s*:\s*['"]([^'"]+)''' % (file_key), fragment, re.DOTALL)
    labels = re.findall(r'''['"]?label['"]?\s*:\s*['"]([^'"]*)''', fragment, re.DOTALL)
    for stream_url, label in zip(files, labels):
        if not stream_url: continue
        
        stream_url = stream_url.replace(r'\/', '/')
        stream_url = unquote(stream_url)
        if get_direct_hostname(scraper, stream_url) == 'gvideo':
            sources[stream_url] = {'quality': gv_get_quality(stream_url), 'direct': True}
        elif label is not None and re.search(r'\d+p?', label, re.I):
            sources[stream_url] = {'quality': height_get_quality(label), 'direct': True}
        elif label is not None:
            sources[stream_url] = {'quality': label, 'direct': True}
        else:
            sources[stream_url] = {'quality': QUALITIES.HIGH, 'direct': True}

    return sources

def get_gk_links(scraper, html, page_url, page_quality, link_url, player_url):
    def get_real_gk_url(scraper, player_url, params):
        html = scraper._http_get(player_url, params=params, headers=XHR, cache_limit=.25)
        js_data = parse_json(html, player_url)
        data = js_data.get('data', {})
        if data is not None and 'files' in data:
            return data['files']
        else:
            return data

    sources = {}
    for attrs, _content in dom_parser2.parse_dom(html, 'a', req=['data-film', 'data-name', 'data-server']):
        data = {'ipplugins': 1, 'ip_film': attrs['data-film'], 'ip_server': attrs['data-server'], 'ip_name': attrs['data-name']}
        headers = {'Referer': page_url}
        headers.update(XHR)
        html = scraper._http_get(link_url, data=data, headers=headers, cache_limit=.25)
        js_data = parse_json(html, link_url)
        params = {'u': js_data.get('s'), 'w': '100%', 'h': 420, 's': js_data.get('v'), 'n': 0}
        stream_urls = get_real_gk_url(scraper, player_url, params)
        if stream_urls is None: continue
        
        if isinstance(stream_urls, str):
            sources[stream_urls] = page_quality
        else:
            for item in stream_urls:
                stream_url = item['files']
                if get_direct_hostname(scraper, stream_url) == 'gvideo':
                    quality = gv_get_quality(stream_url)
                elif 'quality' in item:
                    quality = height_get_quality(item['quality'])
                else:
                    quality = page_quality
                sources[stream_url] = quality
                    
    return sources

def get_files(scraper, url, headers=None, cache_limit=.5):
    sources = []
    for row in parse_directory(scraper, scraper._http_get(url, headers=headers, cache_limit=cache_limit)):
        source_url = urljoin(url, row['link'])
        if row['directory'] and not row['link'].startswith('..'):
            sources += get_files(scraper, source_url, headers={'Referer': url}, cache_limit=cache_limit)
        else:
            row['url'] = source_url
            sources.append(row)
    return sources

def parse_directory(scraper, html):
    rows = []
    for match in re.finditer(scraper.row_pattern, html):
        row = match.groupdict()
        if row['title'].endswith('/'): row['title'] = row['title'][:-1]
        row['directory'] = True if row['link'].endswith('/') else False
        if row['size'] == '-': row['size'] = None
        rows.append(row)
    return rows

def parse_google(scraper, link):
    sources = []
    html = scraper._http_get(link, cache_limit=.25)
    match = re.search(r'pid=([^&]+)', link)
    if match:
        vid_id = match.group(1)
        sources = parse_gplus(vid_id, html, link)
    else:
        if 'drive.google' in link or 'docs.google' in link or 'youtube.googleapis' in link:
            sources = parse_gdocs(scraper, link)
        if 'picasaweb' in link:
            i = link.rfind('#')
            if i > -1:
                link_id = link[i + 1:]
            else:
                link_id = ''
            match = re.search(r'feedPreload:\s*(.*}]}})},', html, re.DOTALL)
            if match:
                js = parse_json(match.group(1), link)
                for item in js['feed']['entry']:
                    if not link_id or item['gphoto$id'] == link_id:
                        for media in item['media']['content']:
                            if media['type'].startswith('video'):
                                sources.append(media['url'].replace('%3D', '='))
            else:
                match = re.search(r'preload\'?:\s*(.*}})},', html, re.DOTALL)
                if match:
                    js = parse_json(match.group(1), link)
                    for media in js['feed']['media']['content']:
                        if media['type'].startswith('video'):
                            sources.append(media['url'].replace('%3D', '='))

    sources = list(set(sources))
    return sources

def parse_gplus(vid_id, html, link=''):
    def extract_video(item):
        vid_sources = []
        for e in item:
            if not isinstance(e, dict): continue
            for key in e:
                for item2 in e[key]:
                    if not isinstance(item2, list): continue
                    for item3 in item2:
                        if not isinstance(item3, list): continue
                        for item4 in item3:
                            if not isinstance(item4, str): continue
                            s = unquote(item4).replace('\\0026', '&').replace('\\003D', '=')
                            for match in re.finditer(r'url=([^&]+)', s):
                                vid_sources.append(match.group(1))
        return vid_sources
    
    sources = []
    match = re.search(r'return\s+(\[\[.*?)\s*}}', html, re.DOTALL)
    if match:
        try:
            js = parse_json(match.group(1), link)
            for top_item in js:
                if not isinstance(top_item, list): continue
                for item in top_item:
                    if not isinstance(item, list): continue
                    for item2 in item:
                        if not isinstance(item2, list): continue
                        for item3 in item2:
                            if item3 == vid_id:
                                sources = extract_video(item2)
                                
        except Exception as e:
            logger.log('Google Plus Parse failure: %s - %s' % (link, e), log_utils.LOGWARNING)
    return sources

def parse_gdocs(scraper, link):
    urls = []
    link = re.sub(r'/preview$', '/view', link)
    html = scraper._http_get(link, cache_limit=.5)
    for match in re.finditer(r'\[\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\]', html):
        key, value = match.groups()
        if key != 'fmt_stream_map': continue
        urls += parse_stream_map(scraper, value)
    
    if not urls:
        doc_id = ''
        query = parse_query(link)
        if 'docid' in query:
            doc_id = query['docid']
        elif '/view' in link:
            match = re.search(r"'id'\s*:\s*'([^']+)", html)
            if match: doc_id = match.group(1)
                
        if doc_id:
            info_url = 'https://drive.google.com/get_video_info'
            html = scraper._http_get(info_url, params={'docid': doc_id}, headers={'Referer': link}, cache_limit=.5)
            if 'status=ok' not in html:
                html = base64.b64decode(html)
            query = parse_query(html)
            urls += parse_stream_map(scraper, query.get('fmt_stream_map', ''))
                
    return urls

def parse_stream_map(scraper, value):
    urls = []
    for item in value.split(','):
        _source_fmt, source_url = item.split('|')
        source_url = source_url.replace('\\u003d', '=').replace('\\u0026', '&')
        source_url = unquote(source_url)
        if scraper is not None:
            source_url += '|Cookie=%s' % (scraper._get_stream_cookies())
        urls.append(source_url)
    return urls
    
def do_recaptcha(scraper, key, tries=None, max_tries=None):
    challenge_url = CAPTCHA_BASE_URL + '/challenge?k=%s' % (key)
    html = scraper._cached_http_get(challenge_url, CAPTCHA_BASE_URL, timeout=DEFAULT_TIMEOUT, cache_limit=0)
    match = re.search(r"challenge\s+\:\s+'([^']+)", html)
    captchaimg = 'http://www.google.com/recaptcha/api/image?c=%s' % (match.group(1))
    img = xbmcgui.ControlImage(450, 0, 400, 130, captchaimg)
    wdlg = xbmcgui.WindowDialog()
    wdlg.addControl(img)
    wdlg.show()
    header = 'Type the words in the image'
    if tries and max_tries:
        header += ' (Try: %s/%s)' % (tries, max_tries)
    solution = kodi.get_keyboard(header)
    if not solution:
        raise Exception('You must enter text in the image to access video')
    wdlg.close()
    return {'recaptcha_challenge_field': match.group(1), 'recaptcha_response_field': solution}

def to_slug(title):
    slug = title.lower()
    slug = re.sub(r'[^A-Za-z0-9 -]', ' ', slug)
    slug = re.sub(r'\s\s+', ' ', slug)
    slug = re.sub(r' ', '-', slug)
    return slug

def parse_query(url):
    q = {}
    queries = parse_qs(urlparse(url).query)
    if not queries: queries = parse_qs(url)
    for key, value in queries.items():
        if len(value) == 1:
            q[key] = value[0]
        else:
            q[key] = value
    return q

def get_days(age):
    age = age.replace('&nbsp;', ' ')
    match = re.search(r'(\d+)\s*(.*)', age)
    units = {'day': 1, 'week': 7, 'month': 30, 'year': 365}
    if match:
        num, unit = match.groups()
        unit = unit.lower()
        if unit.endswith('s'): unit = unit[:-1]
        days = int(num) * units.get(unit, 0)
    else:
        days = 0
        
    return days
