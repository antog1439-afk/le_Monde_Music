# -*- coding: utf-8 -*-
import os
import json
import random
import urllib.parse
import time
import re
import hashlib
from typing import Optional, Dict, Any, List
from datetime import datetime
import requests
import logging
import threading
from bs4 import BeautifulSoup
import io

import telebot
from telebot.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, BotCommand

# === ПЫТАЕМСЯ ИМПОРТИРОВАТЬ PIL ДЛЯ ГЕНЕРАЦИИ ОБЛОЖЕК ===
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# === НАСТРОЙКИ ЛОГГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# === ТОКЕНЫ ===
TELEGRAM_TOKEN = '8586892813:AAE3qgxUtGTfA6kefeuOlPy2bNypojFj6Sw'
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# === НАСТРОЙКИ ===
CACHE_DURATION = 3600
SUBSCRIPTIONS_FILE = 'user_subscriptions.json'
MAX_RETRIES = 5
RETRY_DELAY = 5
CONCERTS_CACHE_DURATION = 3600

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
user_subscriptions = {}
user_track_cache = {}
user_artist_cache = {}
preview_cache = {}
callback_storage = {}
concerts_cache = {}
callback_counter = 0
youtube_cache = {}
audio_cache = {}
audio_cache_time = {}

# === ПЫТАЕМСЯ ИМПОРТИРОВАТЬ YT-DLP ===
try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
    logger.info("✅ yt-dlp установлен")
except ImportError:
    YT_DLP_AVAILABLE = False
    logger.warning("⚠️ yt-dlp НЕ установлен! Установите: pip install yt-dlp")

# === БАЗА ИИ-ФАКТОВ ===
AI_FACTS_DATABASE = {
    "асия": [
        "Настоящее имя Асии — Анастасия Вячеславовна Алентьева",
        "Родилась 1 сентября 1997 года в городе Белово",
        "Останься — 100+ млн прослушиваний",
        "В 2022 году стала артисткой лейбла Effective Records",
        "Трек «911» — один из самых эмоциональных треков Асии",
    ],
    "big baby tape": [
        "Big Baby Tape (Егор Ракитин) родился в Лос-Анджелесе",
        "Трек Gimme The Loot собрал 50+ млн прослушиваний",
        "Участник лейбла Sony Music Russia с 2018 года",
    ],
    "платина": [
        "Платина (Давид Нуриев) — российский рэп-исполнитель",
        "Родился в Санкт-Петербурге",
        "Известен по трекам: Ай, Заберу, Каспий",
    ],
    "моргенштерн": [
        "Алишер Моргенштерн родился в Уфе 17 февраля 1998 года",
        "Самый молодой миллионер в российском шоу-бизнесе",
        "Cadillac — первый трек с 100 млн просмотров",
    ],
    "кино": [
        "Группа Кино основана в 1981 году в Ленинграде",
        "Виктор Цой — легендарный лидер",
        "Группа крови — гимн поколения 90-х",
    ],
    "земфира": [
        "Земфира родилась в Уфе 26 августа 1976 года",
        "Первая женщина, собравшая сольный концерт в Олимпийском",
        "Дебютный альбом разошёлся тиражом 700 000 копий",
    ],
    "imagine dragons": [
        "3 премии Grammy",
        "Radioactive — самый долгоиграющий сингл в истории Billboard",
        "Трек Believer использован в рекламе FIFA",
    ]
}

# === БАЗА СМЫСЛОВ ПЕСЕН ===
SONG_MEANINGS = {
    "останься": {
        "artist": "асия",
        "meaning": "Песня о том, как трудно отпустить человека, который стал частью жизни.",
        "emotion": "💔 Грусть, ностальгия, надежда"
    },
    "твой поцелуй": {
        "artist": "асия",
        "meaning": "Трек о силе первого поцелуя, который остаётся в памяти навсегда.",
        "emotion": "💕 Нежность, романтика, трепет"
    },
    "детство": {
        "artist": "асия",
        "meaning": "Ностальгическая песня о беззаботном времени.",
        "emotion": "🌅 Ностальгия, теплота, грусть"
    },
    "группа крови": {
        "artist": "кино",
        "meaning": "Легендарная песня о поколении, которое ищет свой путь.",
        "emotion": "⚡ Бунт, поиск, свобода"
    },
    "звезда по имени солнце": {
        "artist": "кино",
        "meaning": "Песня о надежде, которая горит внутри каждого человека.",
        "emotion": "☀️ Надежда, свет, вера"
    },
    "believer": {
        "artist": "imagine dragons",
        "meaning": "Песня о преодолении трудностей и вере в себя.",
        "emotion": "💪 Сила, вера, преодоление"
    },
    "radioactive": {
        "artist": "imagine dragons",
        "meaning": "Песня о внутренней силе, которая просыпается после трудных времён.",
        "emotion": "🔥 Восстание, энергия, трансформация"
    },
    "911": {
        "artist": "асия",
        "meaning": "Песня о том, что иногда помощь приходит слишком поздно.",
        "emotion": "😢 Грусть, надежда, боль"
    },
    "21": {
        "artist": "асия",
        "meaning": "Песня о возрасте, когда жизнь только начинается.",
        "emotion": "🌅 Надежда, молодость, энергия"
    }
}

# ====================================================
# === ФУНКЦИИ ДЛЯ РАБОТЫ С ОБЛОЖКАМИ ===
# ====================================================

def generate_fallback_cover(artist: str, title: str) -> Optional[bytes]:
    if not PIL_AVAILABLE:
        return None
    
    try:
        img = Image.new('RGB', (300, 300), color='#1a1a2e')
        draw = ImageDraw.Draw(img)
        
        hash_val = hash(title + artist) % 0xFFFFFF
        r = (hash_val >> 16) & 0xFF
        g = (hash_val >> 8) & 0xFF
        b = hash_val & 0xFF
        
        for i in range(300):
            alpha = i / 300
            color = (
                int(r * (1 - alpha * 0.5)),
                int(g * (1 - alpha * 0.3)),
                int(b * (1 + alpha * 0.2))
            )
            draw.line([(0, i), (300, i)], fill=color)
        
        draw.ellipse([50, 50, 250, 250], outline=(255, 255, 255, 100), width=2)
        draw.ellipse([80, 80, 220, 220], outline=(255, 255, 255, 50), width=1)
        draw.ellipse([130, 80, 160, 110], fill=(255, 255, 255))
        draw.line([145, 110, 145, 200], fill=(255, 255, 255), width=4)
        draw.line([130, 185, 160, 175], fill=(255, 255, 255), width=4)
        
        try:
            font = ImageFont.truetype("arial.ttf", 16)
            font_small = ImageFont.truetype("arial.ttf", 12)
        except:
            font = ImageFont.load_default()
            font_small = font
        
        artist_short = artist[:25] + "..." if len(artist) > 25 else artist
        title_short = title[:30] + "..." if len(title) > 30 else title
        
        draw.text((20, 220), f"🎵 {artist_short}", fill=(255, 255, 255), font=font)
        draw.text((20, 245), f"{title_short}", fill=(200, 200, 200), font=font_small)
        
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        return buffer.getvalue()
        
    except Exception as e:
        logger.error(f"Ошибка генерации обложки-заглушки: {e}")
        return None

def get_cover_from_google_images(artist: str, title: str) -> Optional[bytes]:
    try:
        query = f"{artist} {title} album cover"
        encoded = urllib.parse.quote(query)
        url = f"https://www.google.com/search?q={encoded}&tbm=isch"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        }
        
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        images = soup.find_all('img', {'class': 'rg_i'})
        for img in images[:3]:
            src = img.get('src') or img.get('data-src')
            if src and src.startswith('http'):
                try:
                    img_response = requests.get(src, timeout=5)
                    if img_response.status_code == 200:
                        return img_response.content
                except:
                    continue
        
        return None
        
    except Exception as e:
        logger.debug(f"Ошибка поиска обложки в Google: {e}")
        return None

def get_cover_from_yandex(artist: str, title: str) -> Optional[bytes]:
    try:
        query = f"{artist} {title}"
        encoded_query = urllib.parse.quote(query)
        url = f"https://music.yandex.ru/search?text={encoded_query}&type=all"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        cover_urls = []
        
        images = soup.find_all('img', class_=re.compile(r'cover|track|album|image', re.I))
        for img in images:
            src = img.get('src') or img.get('data-src')
            if src and ('cover' in src.lower() or 'track' in src.lower() or 'album' in src.lower()):
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = 'https://music.yandex.ru' + src
                if src and src.startswith('http'):
                    cover_urls.append(src)
        
        elements = soup.find_all(['div', 'a'], attrs={'data-cover': True})
        for elem in elements:
            cover = elem.get('data-cover')
            if cover and cover.startswith('http'):
                cover_urls.append(cover)
        
        elements_with_style = soup.find_all(style=re.compile(r'background-image.*url', re.I))
        for elem in elements_with_style:
            style = elem.get('style', '')
            match = re.search(r'url\([\'"]?(.*?)[\'"]?\)', style)
            if match:
                cover_url = match.group(1)
                if cover_url and ('cover' in cover_url.lower() or 'track' in cover_url.lower()):
                    if cover_url.startswith('//'):
                        cover_url = 'https:' + cover_url
                    elif cover_url.startswith('/'):
                        cover_url = 'https://music.yandex.ru' + cover_url
                    if cover_url.startswith('http'):
                        cover_urls.append(cover_url)
        
        for cover_url in cover_urls:
            try:
                cover_url = re.sub(r'/\d+x\d+/', '/400x400/', cover_url)
                cover_url = re.sub(r'size=\d+x\d+', 'size=400x400', cover_url)
                
                img_response = requests.get(cover_url, headers=headers, timeout=10)
                if img_response.status_code == 200:
                    content_type = img_response.headers.get('content-type', '')
                    if content_type.startswith('image/'):
                        return img_response.content
            except:
                continue
        
        return None
        
    except Exception as e:
        logger.debug(f"Ошибка получения обложки из Яндекс Музыки: {e}")
        return None

def get_cover_from_deezer(track_id: int) -> Optional[bytes]:
    try:
        url = f"https://api.deezer.com/track/{track_id}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            album = data.get('album', {})
            cover_url = (
                album.get('cover_xl') or
                album.get('cover_big') or
                album.get('cover_medium') or
                album.get('cover_small')
            )
            if cover_url:
                img_response = requests.get(cover_url, timeout=10)
                if img_response.status_code == 200:
                    return img_response.content
    except:
        pass
    return None

def get_cover_data(track_info: Dict[str, Any]) -> Optional[bytes]:
    artist = track_info.get('main_artist', '')
    title = track_info.get('title', '')
    track_id = track_info.get('track_id', 0)
    
    cover_url = track_info.get('cover_url')
    if cover_url:
        try:
            response = requests.get(cover_url, timeout=10)
            if response.status_code == 200:
                return response.content
        except:
            pass
    
    if track_id:
        cover_data = get_cover_from_deezer(track_id)
        if cover_data:
            return cover_data
    
    if artist and title:
        cover_data = get_cover_from_yandex(artist, title)
        if cover_data:
            return cover_data
    
    if artist and title:
        cover_data = get_cover_from_google_images(artist, title)
        if cover_data:
            return cover_data
    
    return generate_fallback_cover(artist, title)

def search_yandex_music_track(artist: str, title: str) -> Optional[Dict[str, Any]]:
    """Ищет трек в Яндекс Музыке (возвращает информацию о треке)"""
    try:
        query = f"{artist} {title}"
        encoded = urllib.parse.quote(query)
        url = f"https://music.yandex.ru/search?text={encoded}&type=all"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ищем трек
        track_link = soup.find('a', href=re.compile(r'/track/\d+'))
        if track_link:
            href = track_link.get('href')
            if href:
                track_url = 'https://music.yandex.ru' + href if href.startswith('/') else href
                
                # Пробуем найти название
                title_elem = soup.find('div', class_=re.compile(r'title|name|track', re.I))
                artist_elem = soup.find('div', class_=re.compile(r'artist|performer|author', re.I))
                
                track_title = title_elem.text.strip() if title_elem else title
                track_artist = artist_elem.text.strip() if artist_elem else artist
                
                # Пробуем найти длительность
                duration_match = re.search(r'(\d+):(\d{2})', soup.text)
                duration = None
                if duration_match:
                    minutes = int(duration_match.group(1))
                    seconds = int(duration_match.group(2))
                    duration = minutes * 60 + seconds
                
                return {
                    'found': True,
                    'title': track_title,
                    'artist': track_artist,
                    'url': track_url,
                    'duration': duration,
                    'duration_str': f"{duration//60}:{duration%60:02d}" if duration else None,
                    'source': 'yandex_music'
                }
        
        return None
        
    except Exception as e:
        logger.error(f"Ошибка поиска в Яндекс Музыке: {e}")
        return None

# ====================================================
# === ОБНОВЛЁННАЯ ФУНКЦИЯ СКАЧИВАНИЯ ПОЛНОГО ТРЕКА ===
# ====================================================

def download_full_track_from_youtube(query: str) -> Optional[bytes]:
    if not YT_DLP_AVAILABLE:
        return None
    
    cache_key = query.lower()
    
    if cache_key in audio_cache:
        if time.time() - audio_cache_time.get(cache_key, 0) < 3600:
            return audio_cache[cache_key]
    
    try:
        ydl_base_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'outtmpl': 'temp_audio.%(ext)s',
            'ignoreerrors': True,
            'no_check_certificate': True,
            'socket_timeout': 30,
            'geo_bypass': True,
            'geo_bypass_country': 'RU',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            }
        }
        
        client_configs = [
            {'player_client': ['ios']},
            {'player_client': ['android']},
            {'player_client': ['mweb']},
            {'player_client': ['web']},
            {'player_client': ['ios_embedded']},
            {'player_client': ['android_embedded']},
        ]
        
        search_queries = [
            f"ytsearch1:{query} official audio",
            f"ytsearch1:{query} audio",
            f"ytsearch1:{query} song",
            f"ytsearch1:{query}",
        ]
        
        for client in client_configs:
            for search_query in search_queries:
                try:
                    opts = ydl_base_opts.copy()
                    opts['extractor_args'] = {'youtube': client}
                    
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(search_query, download=False)
                        
                        if info and info.get('entries'):
                            video = info['entries'][0]
                            video_url = video.get('webpage_url')
                            duration = video.get('duration', 0)
                            
                            if duration and duration < 900 and video_url:
                                with yt_dlp.YoutubeDL(opts) as ydl_download:
                                    ydl_download.extract_info(video_url, download=True)
                                    for ext in ['.m4a', '.webm', '.mp4', '.opus']:
                                        filename = f"temp_audio{ext}"
                                        if os.path.exists(filename):
                                            with open(filename, 'rb') as f:
                                                audio_data = f.read()
                                            os.remove(filename)
                                            audio_cache[cache_key] = audio_data
                                            audio_cache_time[cache_key] = time.time()
                                            logger.info(f"✅ Скачано через {client.get('player_client')}")
                                            return audio_data
                except Exception as e:
                    logger.debug(f"Не сработало: {client} + {search_query}: {e}")
                    continue
        
        if os.path.exists('cookies.txt'):
            for client in client_configs[:4]:
                for search_query in search_queries[:2]:
                    try:
                        opts = ydl_base_opts.copy()
                        opts['cookiefile'] = 'cookies.txt'
                        opts['extractor_args'] = {'youtube': client}
                        
                        with yt_dlp.YoutubeDL(opts) as ydl:
                            info = ydl.extract_info(search_query, download=False)
                            
                            if info and info.get('entries'):
                                video = info['entries'][0]
                                video_url = video.get('webpage_url')
                                duration = video.get('duration', 0)
                                
                                if duration and duration < 900 and video_url:
                                    with yt_dlp.YoutubeDL(opts) as ydl_download:
                                        ydl_download.extract_info(video_url, download=True)
                                        for ext in ['.m4a', '.webm', '.mp4', '.opus']:
                                            filename = f"temp_audio{ext}"
                                            if os.path.exists(filename):
                                                with open(filename, 'rb') as f:
                                                    audio_data = f.read()
                                                os.remove(filename)
                                                audio_cache[cache_key] = audio_data
                                                audio_cache_time[cache_key] = time.time()
                                                logger.info(f"✅ Скачано через cookies.txt с клиентом {client.get('player_client')}")
                                                return audio_data
                    except Exception as e:
                        logger.debug(f"Не сработало: cookies.txt + {client} + {search_query}: {e}")
                        continue
        
        return None
        
    except Exception as e:
        logger.error(f"Ошибка скачивания аудио: {e}")
        return None

# === НОВАЯ ФУНКЦИЯ: ПОИСК В YOUTUBE MUSIC ===
def search_youtube_music(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    results = []
    cache_key = f"yt_{query.lower()}"
    
    if cache_key in youtube_cache:
        cached_data, cached_time = youtube_cache[cache_key]
        if time.time() - cached_time < 3600:
            return cached_data
    
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://music.youtube.com/search?q={encoded_query}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            return results
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        track_elements = soup.find_all(['ytmusic-responsive-list-item-renderer', 'ytmusic-two-row-item-renderer'])
        
        if not track_elements:
            track_elements = soup.find_all('div', class_=re.compile(r'ytmusic|song|track', re.I))
        
        for element in track_elements[:limit]:
            try:
                track_data = parse_youtube_track_element(element)
                if track_data:
                    results.append(track_data)
            except Exception as e:
                continue
        
        if not results:
            links = soup.find_all('a', href=re.compile(r'/watch\?v=', re.I))
            for link in links[:limit]:
                try:
                    href = link.get('href', '')
                    if href and '/watch?v=' in href:
                        title = link.get_text(strip=True)
                        if title and len(title) > 3:
                            results.append({
                                'title': title,
                                'artist': 'YouTube Music',
                                'link': 'https://music.youtube.com' + href if href.startswith('/') else href,
                                'source': 'youtube_music',
                                'is_track': True
                            })
                except:
                    continue
        
        youtube_cache[cache_key] = (results, time.time())
        
        return results
        
    except Exception as e:
        logger.error(f"Ошибка поиска в YouTube Music: {e}")
        return results

def parse_youtube_track_element(element) -> Optional[Dict[str, Any]]:
    try:
        text = element.get_text(' ', strip=True)
        
        title = None
        artist = None
        link = None
        
        link_elem = element.find('a', href=re.compile(r'/watch\?v=', re.I))
        if link_elem:
            href = link_elem.get('href', '')
            if href:
                if href.startswith('/'):
                    link = 'https://music.youtube.com' + href
                else:
                    link = href
        
        lines = text.split('\n')
        lines = [line.strip() for line in lines if line.strip()]
        
        if len(lines) >= 2:
            title = lines[0]
            artist = lines[1] if len(lines) > 1 else None
        
        if not title or not artist:
            match = re.search(r'([А-Яа-яA-Za-z0-9\s\-\.\'\"\(\)]+)\s*[—\-–]\s*([А-Яа-яA-Za-z0-9\s\-\.\'\"\(\)]+)', text)
            if match:
                title = match.group(1).strip()
                artist = match.group(2).strip()
        
        if not title:
            return None
        
        if not artist:
            artist = 'YouTube Music'
        
        return {
            'title': title,
            'artist': artist,
            'link': link,
            'source': 'youtube_music',
            'is_track': True
        }
        
    except Exception as e:
        return None

# === НОВАЯ ФУНКЦИЯ: ПОИСК В YOUTUBE ===
def search_youtube(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    results = []
    
    try:
        encoded_query = urllib.parse.quote(query + " music")
        url = f"https://www.youtube.com/results?search_query={encoded_query}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            return results
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        links = soup.find_all('a', href=re.compile(r'/watch\?v=', re.I))
        for link in links[:limit]:
            try:
                href = link.get('href', '')
                if href and '/watch?v=' in href:
                    title = link.get_text(strip=True)
                    if title and len(title) > 3:
                        results.append({
                            'title': title,
                            'artist': 'YouTube',
                            'link': 'https://www.youtube.com' + href if href.startswith('/') else href,
                            'source': 'youtube',
                            'is_track': True
                        })
            except:
                continue
        
        return results
        
    except Exception as e:
        logger.error(f"Ошибка поиска в YouTube: {e}")
        return results

# === НОВАЯ ФУНКЦИЯ: ПОИСК В ЯНДЕКС МУЗЫКЕ ===
def search_yandex_music(query: str, limit: int = 30) -> List[Dict[str, Any]]:
    results = []
    
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://music.yandex.ru/search?text={encoded_query}&type=all"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            return results
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        track_elements = soup.find_all(['div', 'a'], class_=re.compile(r'track|d-track|track__|typo-track', re.I))
        
        for element in track_elements[:limit]:
            try:
                track_data = parse_yandex_track_element(element)
                if track_data:
                    results.append(track_data)
            except Exception as e:
                continue
        
        if not results:
            album_elements = soup.find_all(['div', 'a'], class_=re.compile(r'album|d-album|album__', re.I))
            for element in album_elements[:limit]:
                try:
                    album_data = parse_yandex_album_element(element, query)
                    if album_data:
                        results.append(album_data)
                except Exception as e:
                    continue
        
        return results
        
    except Exception as e:
        logger.error(f"Ошибка поиска в Яндекс Музыке: {e}")
        return results

def parse_yandex_track_element(element) -> Optional[Dict[str, Any]]:
    try:
        text = element.get_text(' ', strip=True)
        
        title = None
        artist = None
        
        title_match = re.search(r'([А-Яа-яA-Za-z0-9\s\-\.\']+)\s*[—\-]\s*([А-Яа-яA-Za-z0-9\s\-\.\']+)', text)
        if title_match:
            artist = title_match.group(1).strip()
            title = title_match.group(2).strip()
        else:
            parts = text.split('—')
            if len(parts) >= 2:
                artist = parts[0].strip()
                title = parts[1].strip()
        
        if not title or not artist:
            return None
        
        link = None
        link_elem = element.find('a', href=True)
        if link_elem:
            href = link_elem.get('href', '')
            if href and '/track/' in href:
                if href.startswith('/'):
                    link = 'https://music.yandex.ru' + href
                else:
                    link = href
        
        duration = None
        duration_match = re.search(r'(\d+):(\d{2})', text)
        if duration_match:
            minutes = int(duration_match.group(1))
            seconds = int(duration_match.group(2))
            duration = minutes * 60 + seconds
        
        return {
            'title': title,
            'artist': artist,
            'duration': duration,
            'duration_str': f"{duration//60}:{duration%60:02d}" if duration else None,
            'link': link,
            'source': 'yandex'
        }
        
    except Exception as e:
        return None

def parse_yandex_album_element(element, query: str) -> Optional[Dict[str, Any]]:
    try:
        text = element.get_text(' ', strip=True)
        
        title = None
        artist = None
        
        title_match = re.search(r'([А-Яа-яA-Za-z0-9\s\-\.\']+)\s*[—\-]\s*([А-Яа-яA-Za-z0-9\s\-\.\']+)', text)
        if title_match:
            artist = title_match.group(1).strip()
            title = title_match.group(2).strip()
        
        if not title:
            title = query
        
        link = None
        link_elem = element.find('a', href=True)
        if link_elem:
            href = link_elem.get('href', '')
            if href and '/album/' in href:
                if href.startswith('/'):
                    link = 'https://music.yandex.ru' + href
                else:
                    link = href
        
        return {
            'title': title,
            'artist': artist or 'Неизвестный исполнитель',
            'is_album': True,
            'link': link,
            'source': 'yandex'
        }
        
    except Exception as e:
        return None

# === УЛУЧШЕННАЯ ФУНКЦИЯ ПОИСКА ВСЕХ ТРЕКОВ ===
def search_all_tracks(query: str, max_pages: int = 15) -> List[Dict[str, Any]]:
    all_tracks = []
    page = 0
    per_page = 50
    
    search_queries = [query]
    
    if re.match(r'^\d+$', query.strip()):
        search_queries.append(f"{query} трек")
        search_queries.append(f"{query} песня")
        search_queries.append(f"{query} music")
        search_queries.append(f"{query} song")
    elif re.match(r'^\d+', query.strip()):
        search_queries.append(query + " трек")
        search_queries.append(query + " music")
        search_queries.append(query + " song")
    
    for search_query in search_queries:
        if all_tracks:
            break
        
        try:
            page = 0
            while page < max_pages:
                url = f"https://api.deezer.com/search?q={urllib.parse.quote(search_query)}&limit={per_page}&index={page * per_page}&order=RANKING"
                response = requests.get(url, timeout=30)
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                
                if not data.get('data') or len(data['data']) == 0:
                    break
                
                all_tracks.extend(data['data'])
                
                if len(data['data']) < per_page:
                    break
                
                total = data.get('total', 0)
                if len(all_tracks) >= total:
                    break
                
                page += 1
                time.sleep(0.2)
                
        except Exception as e:
            logger.error(f"Ошибка поиска треков для запроса {search_query}: {e}")
            continue
    
    if not all_tracks:
        try:
            artist_search = f"artist:\"{query}\""
            url = f"https://api.deezer.com/search?q={urllib.parse.quote(artist_search)}&limit=50"
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data.get('data'):
                    all_tracks.extend(data['data'])
        except:
            pass
    
    logger.info(f"Найдено {len(all_tracks)} треков для запроса: {query}")
    return all_tracks

# === УЛУЧШЕННАЯ ФУНКЦИЯ ПОИСКА ВСЕХ АЛЬБОМОВ ===
def search_all_albums(query: str, max_pages: int = 10) -> List[Dict[str, Any]]:
    all_albums = []
    page = 0
    per_page = 50
    
    search_queries = [query]
    
    if re.match(r'^\d+$', query.strip()):
        search_queries.append(f"{query} альбом")
        search_queries.append(f"{query} album")
    
    for search_query in search_queries:
        if all_albums:
            break
        
        try:
            page = 0
            while page < max_pages:
                url = f"https://api.deezer.com/search/album?q={urllib.parse.quote(search_query)}&limit={per_page}&index={page * per_page}"
                response = requests.get(url, timeout=30)
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                
                if not data.get('data') or len(data['data']) == 0:
                    break
                
                all_albums.extend(data['data'])
                
                if len(data['data']) < per_page:
                    break
                
                total = data.get('total', 0)
                if len(all_albums) >= total:
                    break
                
                page += 1
                time.sleep(0.2)
                
        except Exception as e:
            logger.error(f"Ошибка поиска альбомов для запроса {search_query}: {e}")
            continue
    
    return all_albums

# ============================================================
# === НОВАЯ ФУНКЦИЯ: ТОЧНЫЙ ПОИСК ПО НАЗВАНИЮ И ИСПОЛНИТЕЛЮ ===
# ============================================================

def search_tracks_by_title(query: str) -> List[Dict[str, Any]]:
    """Ищет все треки с похожим названием ИЛИ исполнителем"""
    try:
        logger.info(f"🔍 search_tracks_by_title: {query}")
        
        all_tracks = search_all_tracks(query, max_pages=3)
        
        if not all_tracks:
            logger.warning(f"❌ Ничего не найдено в Deezer: {query}")
            return []
        
        logger.info(f"🔍 Найдено в Deezer: {len(all_tracks)} треков")
        
        query_lower = query.lower().strip()
        query_words = set(query_lower.split())
        results = []
        
        for track in all_tracks:
            track_title = track.get('title', '').lower().strip()
            artist_name = track.get('artist', {}).get('name', '').lower().strip()
            
            # Нормализуем
            track_title = ' '.join(track_title.split())
            artist_name = ' '.join(artist_name.split())
            
            # ===== СЧИТАЕМ ОЧКИ =====
            score = 0
            
            # 1. Проверяем название трека
            if query_lower in track_title:
                score = 1.0
                logger.info(f"📊 ТОЧНОЕ совпадение по названию: {track_title}")
            elif track_title in query_lower:
                score = 0.8
                logger.info(f"📊 Частичное совпадение по названию: {track_title}")
            else:
                title_words = set(track_title.split())
                match_count = len(title_words & query_words)
                if match_count > 0:
                    score = match_count / len(query_words)
                    logger.info(f"📊 Совпадение по словам: {track_title} (score: {score:.2f})")
            
            # 2. Проверяем исполнителя (ДАЁМ БОЛЬШЕ ОЧКОВ!)
            artist_words = set(artist_name.split())
            artist_match = len(artist_words & query_words)
            if artist_match > 0:
                artist_score = artist_match / len(query_words)
                score = max(score, artist_score * 1.2)  # Исполнитель важнее
                logger.info(f"📊 Совпадение по исполнителю: {artist_name} (score: {score:.2f})")
            
            # 3. Бонус за точное совпадение исполнителя
            if artist_name in query_lower:
                score = max(score, 0.9)
                logger.info(f"📊 Точное совпадение исполнителя: {artist_name}")
            
            # 4. Бонус за точное совпадение названия
            if track_title in query_lower:
                score = max(score, 0.8)
                logger.info(f"📊 Точное совпадение названия: {track_title}")
            
            # 5. Если в запросе есть исполнитель — ищем ТОЛЬКО его
            # Проверяем известных исполнителей
            known_artists = ['big baby tape', 'асия', 'кино', 'imagine dragons']
            for known in known_artists:
                if known in query_lower:
                    # Если запрос содержит известного исполнителя — проверяем, что трек именно его
                    if known in artist_name:
                        score = max(score, 0.8)  # Даём высокий балл
                        logger.info(f"📊 Известный исполнитель {known} совпадает!")
                    else:
                        # Если исполнитель не тот — сильно снижаем балл
                        score = score * 0.3
                        logger.info(f"📊 Исполнитель {artist_name} не совпадает с {known}, снижаем балл")
                    break
            
            logger.info(f"📊 Итоговый score для {track_title} — {artist_name}: {score:.2f}")
            
            # ===== ДОБАВЛЯЕМ В РЕЗУЛЬТАТЫ =====
            if score > 0.3:
                results.append(track)
                logger.info(f"✅ ДОБАВЛЕН: {track_title} — {artist_name} (score: {score:.2f})")
        
        # Сортируем по популярности
        results.sort(key=lambda x: x.get('rank', 0), reverse=True)
        
        logger.info(f"✅ Найдено {len(results)} подходящих треков")
        return results[:10]
        
    except Exception as e:
        logger.error(f"Ошибка поиска треков по названию: {e}")
        return []

# ============================================================
# === НОВАЯ ФУНКЦИЯ: ПОКАЗ СПИСКА ТРЕКОВ ===
# ============================================================

def send_track_selection(message: Message, query: str, tracks: List[Dict[str, Any]]):
    """Показывает список найденных треков с кнопками выбора"""
    bot.send_chat_action(message.chat.id, 'typing')
    
    text = f"🔍 <b>Найдено {len(tracks)} треков</b>\n\n"
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    # Показываем до 10 треков
    for i, track in enumerate(tracks[:10], 1):
        title = track.get('title', 'Без названия')
        artist = track.get('artist', {}).get('name', 'Неизвестный')
        track_id = track.get('id')
        
        # Обрезаем длинные названия
        title_short = title[:25] + '...' if len(title) > 25 else title
        artist_short = artist[:20] + '...' if len(artist) > 20 else artist
        
        text += f"{i}. <b>{artist_short}</b> — {title_short}\n"
        
        if track_id:
            callback_data = f"select_track_{track_id}"
            keyboard.add(InlineKeyboardButton(
                f"🎵 {artist_short} — {title_short}",
                callback_data=callback_data
            ))
    
    # Сохраняем треки в кэш
    for track in tracks:
        track_id = track.get('id')
        if track_id:
            try:
                user_track_cache[track_id] = parse_track_data(track)
            except Exception as e:
                logger.error(f"Ошибка кэширования трека {track_id}: {e}")
    
    # Добавляем кнопку "Отмена"
    keyboard.add(InlineKeyboardButton(
        "❌ Отмена",
        callback_data="cancel_search"
    ))
    
    bot.send_message(
        message.chat.id,
        text,
        parse_mode='HTML',
        reply_markup=keyboard
    )

# ============================================================
# === ФУНКЦИЯ ПОИСКА ТРЕКА (для обратной совместимости) ===
# ============================================================

def search_track_full(query: str) -> Optional[Dict[str, Any]]:
    """ТОЧНЫЙ поиск трека — без приоритетов и популярности"""
    try:
        logger.info(f"🔍 Точный поиск: {query}")
        
        # ===== 1. ИЩЕМ В DEEZER =====
        all_tracks = search_all_tracks(query, max_pages=5)
        
        if not all_tracks:
            logger.warning(f"❌ Ничего не найдено в Deezer: {query}")
            return None
        
        # ===== 2. НОРМАЛИЗУЕМ ЗАПРОС ДЛЯ СРАВНЕНИЯ =====
        query_normalized = query.lower().strip()
        # Убираем лишние пробелы
        query_normalized = ' '.join(query_normalized.split())
        
        # Разбиваем запрос на слова
        query_words = set(query_normalized.split())
        
        # ===== 3. ИЩЕМ ТОЧНОЕ СОВПАДЕНИЕ =====
        best_match = None
        best_score = 0
        
        for track in all_tracks:
            track_title = track.get('title', '').lower().strip()
            artist_name = track.get('artist', {}).get('name', '').lower().strip()
            
            # Нормализуем названия
            track_title = ' '.join(track_title.split())
            artist_name = ' '.join(artist_name.split())
            
            # ===== СЧИТАЕМ СОВПАДЕНИЯ =====
            score = 0
            
            # Проверяем, есть ли исполнитель в запросе
            artist_words = set(artist_name.split())
            artist_match = len(artist_words & query_words)
            
            # Проверяем, есть ли название трека в запросе
            title_words = set(track_title.split())
            title_match = len(title_words & query_words)
            
            # ОЧЕНЬ ВАЖНО: исполнитель должен совпадать ХОТЯ БЫ НА 50%
            if artist_match == 0:
                continue  # Пропускаем треки с неправильным исполнителем
            
            # Считаем общий score
            total_words = len(query_words)
            if total_words > 0:
                score = (artist_match + title_match) / total_words
            
            # Бонус за точное совпадение
            if artist_name in query_normalized and track_title in query_normalized:
                score = 1.0  # Максимальный балл
            elif artist_name in query_normalized:
                score = max(score, 0.7)
            elif track_title in query_normalized:
                score = max(score, 0.5)
            
            # Если нашли лучшее совпадение
            if score > best_score:
                best_score = score
                best_match = track
                logger.info(f"📊 Найдено совпадение: {track_title} — {artist_name} (score: {score:.2f})")
        
        # ===== 4. ЕСЛИ НАШЛИ ХОРОШЕЕ СОВПАДЕНИЕ =====
        if best_match and best_score >= 0.4:  # Минимальный порог
            logger.info(f"✅ Точное совпадение: {best_match.get('title')} — {best_match.get('artist', {}).get('name')}")
            return parse_track_data(best_match)
        
        # ===== 5. ЕСЛИ НЕ НАШЛИ — ВОЗВРАЩАЕМ NONE =====
        logger.warning(f"❌ Точного совпадения нет для: {query}")
        return None
        
    except Exception as e:
        logger.error(f"Ошибка в search_track_full: {e}")
        return None

# ============================================================
# === ФУНКЦИЯ ПОИСКА АЛЬБОМА ===
# ============================================================

def search_album_full(query: str) -> Optional[Dict[str, Any]]:
    try:
        all_albums = search_all_albums(query, max_pages=10)
        
        if all_albums:
            query_lower = query.lower()
            
            for album in all_albums:
                album_title = album.get('title', '').lower()
                
                if album_title == query_lower or query_lower in album_title:
                    return process_album_data(album)
                
                if query_lower.isdigit() and query_lower in album_title:
                    return process_album_data(album)
            
            return process_album_data(all_albums[0])
        
        return None
        
    except Exception as e:
        logger.error(f"Ошибка в search_album_full: {e}")
        return None

# === ОСТАЛЬНЫЕ ФУНКЦИИ ===
def get_relative_time(release_date_str: str) -> Optional[str]:
    if not release_date_str:
        return None
    
    try:
        release_dt = None
        for fmt in ['%Y-%m-%d', '%Y-%m', '%Y']:
            try:
                release_dt = datetime.strptime(release_date_str, fmt)
                break
            except ValueError:
                continue
        
        if release_dt is None:
            return None
        
        now = datetime.now()
        diff = now - release_dt
        
        years = diff.days // 365
        months = diff.days // 30
        weeks = diff.days // 7
        days = diff.days
        
        if years >= 5:
            return f"более {years} лет назад"
        elif years >= 2:
            return f"{years} года назад"
        elif years >= 1:
            return f"{years} год назад"
        elif months >= 6:
            return f"{months} месяцев назад"
        elif months >= 2:
            return f"{months} месяца назад"
        elif months >= 1:
            return f"1 месяц назад"
        elif weeks >= 2:
            return f"{weeks} недели назад"
        elif weeks >= 1:
            return f"1 неделю назад"
        elif days >= 2:
            return f"{days} дня назад"
        elif days >= 1:
            return f"1 день назад"
        else:
            return "только что"
            
    except Exception as e:
        logger.debug(f"Ошибка вычисления относительного времени: {e}")
        return None

def generate_short_callback(action: str, track_id: int, artist: str = "", title: str = "") -> str:
    global callback_counter
    callback_counter += 1
    
    # Обрезаем слишком длинные названия
    if len(title) > 20:
        title = title[:20]
    
    callback = f"{action}_{callback_counter}"
    
    callback_storage[callback] = {
        'track_id': track_id,
        'artist': artist[:30] if artist else '',  # Обрезаем
        'title': title[:30] if title else '',     # Обрезаем
        'action': action
    }
    
    return callback

def get_track_preview(track_id: int) -> Optional[str]:
    if track_id in preview_cache:
        return preview_cache[track_id]
    
    try:
        url = f"https://api.deezer.com/track/{track_id}"
        response = requests.get(url, timeout=15)
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        preview_url = data.get('preview')
        
        if preview_url:
            preview_cache[track_id] = preview_url
        
        return preview_url
    except Exception as e:
        logger.error(f"Ошибка получения превью: {e}")
        return None

def get_song_meaning(track_name: str, artist_name: str) -> Optional[Dict[str, Any]]:
    track_lower = track_name.lower()
    artist_lower = artist_name.lower()
    
    for key, meaning in SONG_MEANINGS.items():
        if key in track_lower or track_lower in key:
            if meaning.get('artist', '').lower() in artist_lower or artist_lower in meaning.get('artist', '').lower():
                return meaning
    
    for key, meaning in SONG_MEANINGS.items():
        if key in track_lower:
            return meaning
    
    return None

def encode_callback_data(data: str) -> str:
    if not data:
        return "empty"
    
    cleaned = re.sub(r'[^a-zA-Zа-яА-Я0-9\s\-]', '', data)
    cleaned = cleaned.replace(' ', '_')
    if len(cleaned) > 60:
        cleaned = cleaned[:60]
    if not cleaned:
        cleaned = "unknown"
    
    return cleaned

def format_release_date(date_str: str) -> str:
    if not date_str:
        return None
    
    try:
        for fmt in ['%Y-%m-%d', '%Y-%m', '%Y']:
            try:
                dt = datetime.strptime(date_str, fmt)
                if fmt == '%Y-%m-%d':
                    return dt.strftime('%d %B %Y')
                elif fmt == '%Y-%m':
                    return dt.strftime('%B %Y')
                else:
                    return dt.strftime('%Y')
            except ValueError:
                continue
        return date_str
    except:
        return date_str

# === ОБРАБОТКА ДАННЫХ АЛЬБОМА ===
def process_album_data(album: Dict[str, Any]) -> Dict[str, Any]:
    album_id = album['id']
    album_title = album['title']
    artist_name = album['artist']['name']
    cover_url = album.get('cover_xl') or album.get('cover_big') or album.get('cover_medium')
    release_date = album.get('release_date', '')
    year = release_date.split('-')[0] if release_date else None
    track_count = album.get('nb_tracks', 0)
    
    tracks = []
    try:
        tracks_data = get_all_album_tracks(album_id)
        for track in tracks_data[:30]:
            track_artist = track.get('artist', {}).get('name', artist_name)
            tracks.append({
                'id': track.get('id'),
                'title': track.get('title', 'Без названия'),
                'duration': track.get('duration', 0),
                'preview': track.get('preview'),
                'artist': track_artist
            })
    except Exception as e:
        logger.warning(f"Ошибка получения треков альбома: {e}")
    
    album_link = album.get('link', f"https://www.deezer.com/album/{album_id}")
    
    return {
        'id': album_id,
        'title': album_title,
        'artist': artist_name,
        'cover_url': cover_url,
        'year': year,
        'release_date': release_date,
        'track_count': track_count,
        'tracks': tracks,
        'link': album_link,
        'source': 'deezer'
    }

def get_all_album_tracks(album_id: int) -> List[Dict[str, Any]]:
    all_tracks = []
    page = 0
    per_page = 50
    
    try:
        while True:
            url = f"https://api.deezer.com/album/{album_id}/tracks?limit={per_page}&index={page * per_page}"
            response = requests.get(url, timeout=30)
            
            if response.status_code != 200:
                break
            
            data = response.json()
            
            if not data.get('data') or len(data['data']) == 0:
                break
            
            all_tracks.extend(data['data'])
            
            if len(data['data']) < per_page:
                break
            
            page += 1
            time.sleep(0.1)
        
        return all_tracks
        
    except Exception as e:
        logger.error(f"Ошибка получения треков альбома: {e}")
        return all_tracks

# === ПАРСИНГ ДАННЫХ ТРЕКА ===
def parse_track_data(track: Dict) -> Dict[str, Any]:
    artist_name = track['artist']['name']
    track_title = track['title']
    preview_url = track.get('preview')
    track_id = track['id']
    duration = track.get('duration', 0)
    
    cover_url = None
    if track.get('album'):
        cover_url = (
            track['album'].get('cover_xl') or
            track['album'].get('cover_big') or
            track['album'].get('cover_medium') or
            track['album'].get('cover_small')
        )
    
    album = track.get('album', {})
    album_title = album.get('title', 'Неизвестный альбом')
    release_date = album.get('release_date', '')
    year = release_date.split('-')[0] if release_date else None
    
    if not release_date and album.get('id'):
        try:
            album_url = f"https://api.deezer.com/album/{album['id']}"
            album_response = requests.get(album_url, timeout=15)
            if album_response.status_code == 200:
                album_data = album_response.json()
                if album_data.get('release_date'):
                    release_date = album_data['release_date']
                    year = release_date.split('-')[0] if release_date else None
        except:
            pass
    
    formatted_date = format_release_date(release_date)
    
    encoded_search = urllib.parse.quote(f"{artist_name} {track_title}")
    links = {
        'yandex': f"https://music.yandex.ru/search?text={encoded_search}",
        'youtube_music': f"https://music.youtube.com/search?q={encoded_search}",
        'youtube': f"https://www.youtube.com/results?search_query={encoded_search}+music",
        'deezer': f"https://www.deezer.com/track/{track_id}"
    }
    
    minutes = duration // 60
    seconds = duration % 60
    duration_str = f"{minutes}:{seconds:02d}"
    
    track_data = {
        'title': track_title,
        'artists': artist_name,
        'main_artist': artist_name,
        'album': album_title,
        'year': year,
        'release_date': release_date,
        'formatted_date': formatted_date,
        'track_id': track_id,
        'links': links,
        'preview_url': preview_url,
        'duration': duration,
        'duration_str': duration_str,
        'cover_url': cover_url,
        'explicit': track.get('explicit_lyrics', False),
        'source': 'deezer'
    }
    
    user_track_cache[track_id] = track_data
    return track_data

# === ФУНКЦИЯ ПОЛУЧЕНИЯ БИОГРАФИИ ИЗ DEEZER ===
def get_artist_bio_deezer(artist_name: str) -> Optional[Dict[str, Any]]:
    try:
        search_url = f"https://api.deezer.com/search/artist?q={urllib.parse.quote(artist_name)}&limit=1"
        response = requests.get(search_url, timeout=15)
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        
        if not data.get('data') or len(data['data']) == 0:
            return None
        
        artist = data['data'][0]
        artist_id = artist['id']
        
        artist_url = f"https://api.deezer.com/artist/{artist_id}"
        artist_response = requests.get(artist_url, timeout=15)
        
        if artist_response.status_code != 200:
            return None
        
        artist_data = artist_response.json()
        
        bio = artist_data.get('description', '')
        picture = artist_data.get('picture_xl') or artist_data.get('picture_big') or artist_data.get('picture_medium')
        nb_fan = artist_data.get('nb_fan', 0)
        nb_album = artist_data.get('nb_album', 0)
        link = artist_data.get('link', f"https://www.deezer.com/artist/{artist_id}")
        
        return {
            'name': artist_data.get('name', artist_name),
            'bio': bio,
            'picture': picture,
            'link': link,
            'nb_fan': nb_fan,
            'nb_album': nb_album,
            'id': artist_id
        }
        
    except Exception as e:
        logger.error(f"Ошибка получения биографии из Deezer: {e}")
        return None

# === ФУНКЦИЯ ПОЛУЧЕНИЯ ВСЕХ АЛЬБОМОВ ИСПОЛНИТЕЛЯ ===
def get_artist_albums(artist_name: str, limit: int = 50) -> Optional[List[Dict[str, Any]]]:
    try:
        search_url = f"https://api.deezer.com/search/artist?q={urllib.parse.quote(artist_name)}&limit=1"
        search_response = requests.get(search_url, timeout=15)
        
        if search_response.status_code != 200:
            return None
        
        search_data = search_response.json()
        if not search_data.get('data') or len(search_data['data']) == 0:
            return None
        
        artist_id = search_data['data'][0]['id']
        
        all_albums = []
        page = 0
        per_page = 50
        
        while len(all_albums) < limit:
            url = f"https://api.deezer.com/artist/{artist_id}/albums?limit={per_page}&index={page * per_page}"
            response = requests.get(url, timeout=30)
            
            if response.status_code != 200:
                break
            
            data = response.json()
            
            if not data.get('data') or len(data['data']) == 0:
                break
            
            all_albums.extend(data['data'])
            
            if data.get('total', 0) <= len(all_albums):
                break
            
            page += 1
            
            if page > 10:
                break
        
        return all_albums[:limit]
        
    except Exception as e:
        logger.error(f"Ошибка получения альбомов: {e}")
        return None

def get_album_tracks(album_id: int) -> Optional[List[Dict[str, Any]]]:
    try:
        url = f"https://api.deezer.com/album/{album_id}/tracks"
        response = requests.get(url, timeout=30)
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        return data.get('data', [])
        
    except Exception as e:
        logger.error(f"Ошибка получения треков альбома: {e}")
        return None

def get_album_info(album_id: int) -> Optional[Dict[str, Any]]:
    try:
        url = f"https://api.deezer.com/album/{album_id}"
        response = requests.get(url, timeout=30)
        
        if response.status_code != 200:
            return None
        
        return response.json()
        
    except Exception as e:
        logger.error(f"Ошибка получения информации об альбоме: {e}")
        return None

# === ФУНКЦИЯ ПОЛУЧЕНИЯ ВСЕХ ТРЕКОВ ИСПОЛНИТЕЛЯ ===
def get_all_artist_tracks(artist_name: str, limit: int = 200) -> Optional[List[Dict[str, Any]]]:
    all_tracks = []
    page = 0
    per_page = 50
    
    try:
        while len(all_tracks) < limit:
            url = f"https://api.deezer.com/search?q={urllib.parse.quote(artist_name)}&limit={per_page}&index={page * per_page}&order=RANKING"
            response = requests.get(url, timeout=30)
            
            if response.status_code != 200:
                break
            
            data = response.json()
            
            if not data.get('data') or len(data['data']) == 0:
                break
            
            all_tracks.extend(data['data'])
            
            if data.get('total', 0) <= len(all_tracks):
                break
            
            page += 1
            
            if page > 10:
                break
        
        return all_tracks[:limit]
        
    except Exception as e:
        logger.error(f"Ошибка получения всех треков: {e}")
        return None

# === ФУНКЦИЯ ПОЛУЧЕНИЯ БИОГРАФИИ ИЗ ЯНДЕКС МУЗЫКИ ===
def get_artist_bio_from_yandex(artist_name: str) -> Optional[Dict[str, Any]]:
    try:
        encoded_name = urllib.parse.quote(artist_name)
        url = f"https://music.yandex.ru/artist/{encoded_name}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        result = {
            'name': artist_name,
            'bio': '',
            'photo_url': None,
            'listeners': None,
            'social_links': {},
            'tracks': []
        }
        
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    if data.get('@type') in ['MusicGroup', 'Artist', 'Person']:
                        if data.get('name'):
                            result['name'] = data['name']
                        if data.get('description'):
                            result['bio'] = data['description'].strip()
                        if data.get('image'):
                            if isinstance(data['image'], list):
                                result['photo_url'] = data['image'][0]
                            else:
                                result['photo_url'] = data['image']
                        break
            except:
                pass
        
        if not result['bio']:
            meta = soup.find('meta', {'name': 'description'})
            if meta and meta.get('content'):
                bio = meta['content']
                bio = re.sub(r'Слушайте|на Яндекс Музыке|бесплатно|онлайн|🎵', '', bio, flags=re.IGNORECASE)
                bio = re.sub(r'\s+', ' ', bio).strip()
                result['bio'] = bio
        
        text = soup.get_text()
        match = re.search(r'(\d+[\s\d]*)\s*слушателей', text, re.IGNORECASE)
        if match:
            result['listeners'] = match.group(1).strip()
        
        if not result['photo_url']:
            photo_elem = soup.find('img', class_=re.compile(r'cover|avatar|photo|image|artist', re.I))
            if photo_elem:
                photo_url = photo_elem.get('src') or photo_elem.get('data-src')
                if photo_url:
                    if photo_url.startswith('//'):
                        photo_url = 'https:' + photo_url
                    elif photo_url.startswith('/'):
                        photo_url = 'https://music.yandex.ru' + photo_url
                    photo_url = re.sub(r'/\d+x\d+/', '/400x400/', photo_url)
                    result['photo_url'] = photo_url
        
        social_patterns = {
            'telegram': ['t.me', 'telegram', 'tg'],
            'instagram': ['instagram.com', 'insta'],
            'youtube': ['youtube.com', 'youtu.be'],
            'vk': ['vk.com', 'vkontakte'],
            'tiktok': ['tiktok.com'],
            'twitter': ['twitter.com', 'x.com'],
        }
        
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.text.strip()
            for platform, keywords in social_patterns.items():
                if any(keyword in href.lower() for keyword in keywords):
                    if href.startswith('/'):
                        href = 'https://music.yandex.ru' + href
                    if text:
                        result['social_links'][platform] = {
                            'url': href,
                            'text': text
                        }
                    break
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка получения биографии из Яндекс Музыки: {e}")
        return None

# === ФУНКЦИЯ ДЛЯ ОТПРАВКИ БИОГРАФИИ ===
def send_artist_bio(message: Message, artist_name: str):
    bot.send_chat_action(message.chat.id, 'typing')
    
    cache_key = artist_name.lower()
    if cache_key in user_artist_cache:
        info = user_artist_cache[cache_key]
    else:
        info = get_artist_bio_deezer(artist_name)
        if info:
            user_artist_cache[cache_key] = info
    
    if not info:
        bot.reply_to(
            message,
            f"❌ Не удалось найти информацию об исполнителе: {artist_name}\n\n"
            f"💡 Попробуйте уточнить имя\n\n"
            f"🔍 <a href='https://www.deezer.com/search/{urllib.parse.quote(artist_name)}'>Поиск в Deezer</a>",
            parse_mode='HTML',
            disable_web_page_preview=True
        )
        return
    
    bio_text = f"🎤 <b>{info['name']}</b>\n\n"
    
    if info.get('bio'):
        bio = info['bio']
        if len(bio) > 800:
            bio = bio[:800] + "..."
        bio_text += f"{bio}\n\n"
    else:
        bio_text += "📝 Биография временно недоступна.\n\n"
    
    if info.get('nb_fan'):
        bio_text += f"👥 Фанатов: {info['nb_fan']:,}\n"
    if info.get('nb_album'):
        bio_text += f"💿 Альбомов: {info['nb_album']}\n"
    
    bio_text += f"\n📡 Источник: Deezer"
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    if info.get('link'):
        keyboard.add(InlineKeyboardButton(
            "🎧 Подробнее на Deezer",
            url=info['link']
        ))
    
    keyboard.add(InlineKeyboardButton(
        "🔍 Яндекс.Музыка",
        url=f"https://music.yandex.ru/search?text={urllib.parse.quote(info['name'])}"
    ))
    
    keyboard.add(InlineKeyboardButton(
        "▶️ YouTube Music",
        url=f"https://music.youtube.com/search?q={urllib.parse.quote(info['name'])}"
    ))
    
    keyboard.add(InlineKeyboardButton(
        "📱 Открыть Mini App",
        web_app=WebAppInfo(url="https://antog1439-afk.github.io/Muzyka/")
    ))
    
    concert_info = check_concerts_yandex_music(artist_name)
    encoded_name = urllib.parse.quote(artist_name)
    keyboard.add(InlineKeyboardButton(
        concert_info['message'],
        callback_data=f"show_concerts_{encoded_name}"
    ))
    
    if info.get('picture'):
        try:
            photo_response = requests.get(info['picture'], timeout=15)
            if photo_response.status_code == 200:
                bot.send_photo(
                    message.chat.id,
                    photo=photo_response.content,
                    caption=bio_text,
                    parse_mode='HTML',
                    reply_markup=keyboard
                )
                return
        except Exception as e:
            logger.error(f"Ошибка отправки фото: {e}")
    
    bot.send_message(
        message.chat.id,
        bio_text,
        parse_mode='HTML',
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

# === ФУНКЦИИ ДЛЯ ФОРМАТИРОВАНИЯ ДАТЫ КОНЦЕРТОВ ===
def format_concert_date_short(date_str: str) -> str:
    if not date_str:
        return ''
    
    try:
        months_ru = {
            'Jan': 'янв', 'Feb': 'фев', 'Mar': 'мар', 'Apr': 'апр',
            'May': 'май', 'Jun': 'июн', 'Jul': 'июл', 'Aug': 'авг',
            'Sep': 'сен', 'Oct': 'окт', 'Nov': 'ноя', 'Dec': 'дек'
        }
        weekday_ru = {
            'Mon': 'пн', 'Tue': 'вт', 'Wed': 'ср', 'Thu': 'чт',
            'Fri': 'пт', 'Sat': 'сб', 'Sun': 'вс'
        }
        
        date_formats = ['%Y-%m-%d', '%d.%m.%Y', '%d %B %Y', '%d %b %Y']
        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                month_eng = dt.strftime('%b')
                month_ru = months_ru.get(month_eng, month_eng.lower())
                day = dt.strftime('%d')
                weekday_eng = dt.strftime('%a')
                weekday = weekday_ru.get(weekday_eng, weekday_eng.lower())
                return f"{month_ru}{day}{weekday}"
            except:
                continue
        
        numbers = re.findall(r'\d+', date_str)
        if len(numbers) >= 2:
            day = numbers[0]
            month_num = int(numbers[1])
            months = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
            if 1 <= month_num <= 12:
                month_short = months[month_num - 1]
                return f"{month_short}{day}"
        
        return date_str
    except:
        return date_str

# === ФУНКЦИИ ДЛЯ ПАРСИНГА КОНЦЕРТОВ ===
def parse_concerts_from_yandex(artist_name: str) -> List[Dict[str, Any]]:
    try:
        encoded_name = urllib.parse.quote(artist_name)
        url = f"https://music.yandex.ru/artist/{encoded_name}?tab=concerts"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        concerts = []
        
        concert_blocks = soup.find_all(['div', 'article'], class_=re.compile(r'concert|event|show|ticket|item', re.I))
        
        for block in concert_blocks:
            concert = parse_concert_block(block)
            if concert:
                concerts.append(concert)
        
        if concerts:
            return concerts
        
        concerts = get_concerts_from_afisha_api(artist_name)
        return concerts
        
    except Exception as e:
        logger.error(f"Ошибка парсинга концертов: {e}")
        return []

def parse_concert_block(block) -> Optional[Dict[str, Any]]:
    try:
        concert = {}
        block_text = block.get_text(' ', strip=True)
        
        city_elem = block.find(['span', 'div'], class_=re.compile(r'city|town|place-city', re.I))
        if city_elem:
            concert['city'] = city_elem.text.strip()
        
        date_elem = block.find(['time', 'span'], class_=re.compile(r'date|time|datetime', re.I))
        if date_elem:
            date_text = date_elem.text.strip()
            concert['date'] = date_text
            concert['datetime'] = date_elem.get('datetime', '')
            time_match = re.search(r'(\d{2}:\d{2})', date_text)
            if time_match:
                concert['time'] = time_match.group(1)
        
        venue_elem = block.find(['span', 'div'], class_=re.compile(r'venue|place|location|address', re.I))
        if venue_elem:
            concert['venue'] = venue_elem.text.strip()
        
        price_match = re.search(r'(\d+[\s\d]*)\s*[₽руб]', block_text)
        if price_match:
            concert['price'] = price_match.group(1).strip()
        
        age_match = re.search(r'(\d+\+)', block_text)
        if age_match:
            concert['age'] = age_match.group(1)
        
        cashback_match = re.search(r'Кешбэк\s*до\s*(\d+)%', block_text, re.IGNORECASE)
        if cashback_match:
            concert['cashback'] = f"Кешбэк до {cashback_match.group(1)}%"
        
        link_elem = block.find('a', href=re.compile(r'ticket|buy|order|afisha', re.I))
        if link_elem:
            href = link_elem.get('href', '')
            if href.startswith('/'):
                href = 'https://music.yandex.ru' + href
            concert['ticket_url'] = href
        
        if not concert.get('city'):
            cities = ['Москва', 'Санкт-Петербург', 'Екатеринбург', 'Казань', 'Новосибирск', 'Красноярск', 'Сочи']
            for city in cities:
                if city in block_text:
                    concert['city'] = city
                    break
        
        if concert.get('city') or concert.get('venue') or concert.get('date'):
            return concert
        
    except Exception as e:
        logger.warning(f"Ошибка парсинга блока: {e}")
    
    return None

def get_concerts_from_afisha_api(artist_name: str) -> List[Dict[str, Any]]:
    try:
        encoded_name = urllib.parse.quote(artist_name)
        url = f"https://afisha.yandex.ru/api/v2/events/?text={encoded_name}&type=concert"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return []
        
        data = response.json()
        concerts = []
        
        for event in data.get('items', []):
            concert = {
                'city': event.get('place', {}).get('address', {}).get('city', 'Москва'),
                'venue': event.get('place', {}).get('name', ''),
                'date': event.get('date', {}).get('text', ''),
                'datetime': event.get('date', {}).get('value', ''),
                'price': event.get('price', {}).get('text', ''),
                'ticket_url': event.get('url', ''),
                'age': event.get('age_restriction', ''),
            }
            if concert['datetime']:
                time_match = re.search(r'(\d{2}:\d{2})', concert['datetime'])
                if time_match:
                    concert['time'] = time_match.group(1)
            concerts.append(concert)
        
        return concerts
        
    except Exception as e:
        logger.error(f"Ошибка получения данных с Афиши: {e}")
        return []

def format_concerts_text(artist_name: str, concerts: List[Dict[str, Any]]) -> str:
    if not concerts:
        return f"❌ Не найдено концертов у {artist_name}\n\n💡 Попробуйте позже или проверьте имя исполнителя"
    
    text = f"🎤 <b>{artist_name.upper()} – КОНЦЕРТЫ</b>\n"
    text += f"Найдено: {len(concerts)}\n"
    text += f"Страница в Яндекс.Музыке\n\n"
    
    for i, concert in enumerate(concerts, 1):
        text += f"{i}. "
        
        city = concert.get('city', 'Москва')
        text += f"{city} "
        
        date = concert.get('date', '')
        if date and date != 'Дата уточняется':
            date_short = format_concert_date_short(date)
            if date_short:
                text += f"{date_short} "
        
        venue = concert.get('venue', '')
        if venue:
            text += f"{venue} "
        
        time_str = concert.get('time', '')
        if time_str:
            text += f"• {time_str} "
        
        age = concert.get('age', '')
        if age:
            text += f"• {age} "
        
        cashback = concert.get('cashback', '')
        if cashback:
            text += f"• {cashback} "
        
        price = concert.get('price', '')
        if price:
            price_clean = re.sub(r'[^\d]', '', str(price)).strip()
            if price_clean:
                text += f"от {price_clean} ₽ "
            else:
                text += f"{price} "
        
        if i < len(concerts):
            text += "\n"
    
    if concerts:
        text += "\n\nДата уточняется\n"
        text += "Москва\n"
        text += "500 ₽\n"
        if concerts[0].get('ticket_url'):
            text += "Билеты"
    
    return text

def get_cached_concerts(artist_name: str) -> Dict[str, Any]:
    cache_key = artist_name.lower()
    current_time = time.time()
    
    if cache_key in concerts_cache:
        cached_data, cached_time = concerts_cache[cache_key]
        if current_time - cached_time < CONCERTS_CACHE_DURATION:
            return cached_data
    
    concerts = parse_concerts_from_yandex(artist_name)
    
    result = {
        'artist': artist_name,
        'concerts': concerts,
        'count': len(concerts),
        'formatted_text': format_concerts_text(artist_name, concerts)
    }
    
    concerts_cache[cache_key] = (result, current_time)
    
    return result

# === ФУНКЦИЯ КОНЦЕРТОВ ===
def get_yandex_music_artist_link(artist_name: str) -> str:
    encoded_name = urllib.parse.quote(artist_name)
    return f"https://music.yandex.ru/artist/{encoded_name}"

def get_yandex_music_concerts_link(artist_name: str) -> str:
    encoded_name = urllib.parse.quote(artist_name)
    return f"https://music.yandex.ru/artist/{encoded_name}?tab=concerts"

def check_concerts_yandex_music(artist_name: str) -> Dict[str, Any]:
    try:
        concert_data = get_cached_concerts(artist_name)
        artist_url = get_yandex_music_artist_link(artist_name)
        concerts_url = get_yandex_music_concerts_link(artist_name)
        has_concerts = concert_data['count'] > 0
        
        return {
            'has_concerts': has_concerts,
            'url': artist_url,
            'concerts_url': concerts_url,
            'count': concert_data['count'],
            'message': f"🎫 Найдено {concert_data['count']} концертов" if has_concerts else "🎫 Концерты в Яндекс Музыке",
            'concerts': concert_data['concerts'],
            'formatted_text': concert_data['formatted_text']
        }
        
    except Exception as e:
        logger.error(f"Ошибка проверки концертов: {e}")
        artist_url = get_yandex_music_artist_link(artist_name)
        concerts_url = get_yandex_music_concerts_link(artist_name)
        return {
            'has_concerts': False,
            'url': artist_url,
            'concerts_url': concerts_url,
            'count': 0,
            'message': "🎫 Концерты в Яндекс Музыке",
            'concerts': [],
            'formatted_text': f"❌ Ошибка при поиске концертов {artist_name}"
        }

# === ФУНКЦИИ ДЛЯ АЛЬБОМОВ ===
def send_artist_albums(message: Message, artist_name: str, page: int = 0):
    bot.send_chat_action(message.chat.id, 'typing')
    
    all_albums = get_artist_albums(artist_name, limit=50)
    
    if not all_albums:
        bot.reply_to(
            message,
            f"❌ Не удалось найти альбомы исполнителя: {artist_name}\n\n"
            f"💡 Попробуйте уточнить имя",
            parse_mode='HTML'
        )
        return
    
    all_albums.sort(key=lambda x: x.get('release_date', ''), reverse=True)
    
    per_page = 5
    total_pages = (len(all_albums) + per_page - 1) // per_page
    
    if page >= total_pages:
        page = total_pages - 1
    
    start_idx = page * per_page
    end_idx = min(start_idx + per_page, len(all_albums))
    page_albums = all_albums[start_idx:end_idx]
    
    text = f"💿 <b>АЛЬБОМЫ: {artist_name}</b>\n\n"
    text += f"📄 <b>Страница {page + 1}/{total_pages}</b>\n"
    text += f"📊 <b>Всего:</b> {len(all_albums)} альбомов\n\n"
    
    for i, album in enumerate(page_albums, start_idx + 1):
        title = album.get('title', 'Без названия')
        release_date = album.get('release_date', '')
        year = release_date.split('-')[0] if release_date else 'Неизвестно'
        track_count = album.get('nb_tracks', 0)
        
        text += f"{i}. <b>{title}</b>\n"
        text += f"   📅 {year} • 🎵 {track_count} треков\n\n"
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    encoded_artist = encode_callback_data(artist_name)
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(
            "◀️",
            callback_data=f"albums_page_{encoded_artist}_{page - 1}"
        ))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(
            "▶️",
            callback_data=f"albums_page_{encoded_artist}_{page + 1}"
        ))
    
    if nav_buttons:
        keyboard.add(*nav_buttons)
    
    album_buttons = []
    for album in page_albums:
        album_id = album.get('id')
        album_title = album.get('title', '')
        if album_id:
            album_buttons.append(InlineKeyboardButton(
                f"📀 {album_title[:18]}",
                callback_data=f"album_detail_{album_id}_{encoded_artist}"
            ))
    
    for i in range(0, len(album_buttons), 2):
        if i + 1 < len(album_buttons):
            keyboard.row(album_buttons[i], album_buttons[i + 1])
        else:
            keyboard.row(album_buttons[i])
    
    concert_info = check_concerts_yandex_music(artist_name)
    encoded_name = urllib.parse.quote(artist_name)
    keyboard.add(InlineKeyboardButton(
        f"🎫 {concert_info['message']}",
        callback_data=f"show_concerts_{encoded_name}"
    ))
    
    keyboard.add(InlineKeyboardButton(
        "🎧 Открыть в Deezer",
        url=f"https://www.deezer.com/search/{urllib.parse.quote(artist_name)}"
    ))
    
    if page_albums and page_albums[0].get('cover_medium'):
        try:
            cover_url = page_albums[0]['cover_medium']
            cover_response = requests.get(cover_url, timeout=15)
            if cover_response.status_code == 200:
                bot.send_photo(
                    message.chat.id,
                    photo=cover_response.content,
                    caption=text,
                    parse_mode='HTML',
                    reply_markup=keyboard
                )
                return
        except Exception as e:
            logger.error(f"Ошибка отправки обложки: {e}")
    
    bot.send_message(
        message.chat.id,
        text,
        parse_mode='HTML',
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

def send_album_detail(message: Message, album_id: int, artist_name: str):
    bot.send_chat_action(message.chat.id, 'typing')
    
    album_info = get_album_info(album_id)
    if not album_info:
        bot.reply_to(message, "❌ Не удалось найти информацию об альбоме")
        return
    
    album_tracks = get_all_album_tracks(album_id)
    
    album_artist = album_info.get('artist', {}).get('name', artist_name)
    
    text = f"💿 <b>{album_info.get('title', 'Без названия')}</b>\n\n"
    text += f"🎤 <b>Исполнитель альбома:</b> {album_artist}\n"
    
    release_date = album_info.get('release_date', '')
    if release_date:
        formatted = format_release_date(release_date)
        if formatted:
            text += f"📅 <b>Дата релиза:</b> {formatted}"
            relative_time = get_relative_time(release_date)
            if relative_time:
                text += f"  <i>({relative_time})</i>"
            text += "\n"
    
    text += f"🎵 <b>Треков:</b> {len(album_tracks) if album_tracks else 0}\n\n"
    text += f"📋 <b>ТРЕКЛИСТ:</b>\n\n"
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    if album_tracks:
        for i, track in enumerate(album_tracks[:30], 1):
            track_id = track.get('id')
            title = track.get('title', 'Без названия')
            duration = track.get('duration', 0)
            minutes = duration // 60
            seconds = duration % 60
            duration_str = f"{minutes}:{seconds:02d}"
            
            track_artist = track.get('artist', {}).get('name', album_artist)
            
            if track_artist.lower() != album_artist.lower():
                text += f"{i}. <b>{track_artist}</b> — {title} ⏱ {duration_str} 🤝\n"
            else:
                text += f"{i}. <b>{track_artist}</b> — {title} ⏱ {duration_str}\n"
            
            if track_id:
                short_title = title[:15] if len(title) > 15 else title
                short_artist = track_artist[:15] if len(track_artist) > 15 else track_artist

                play_callback = generate_short_callback('play', track_id, track_artist, title)
                full_track_callback = f"ft_{track_id}"
                
                keyboard.row(
                    InlineKeyboardButton(f"🎧 30 сек", callback_data=play_callback),
                    InlineKeyboardButton(f"🎵 Полный — {short_title[:12]}", callback_data=full_track_callback)
                )
    
    if len(album_tracks) > 30:
        text += f"\n... и еще {len(album_tracks) - 30} треков"
    
    text += f"\n\n🎧 <b>Слушать на платформах:</b>"
    
    platform_buttons = []
    platform_emoji = {
        'yandex': '🎵',
        'youtube_music': '▶️',
        'youtube': '📺',
        'deezer': '🎧'
    }
    platform_names = {
        'yandex': 'Яндекс.Музыка',
        'youtube_music': 'YouTube Music',
        'youtube': 'YouTube',
        'deezer': 'Deezer'
    }
    
    search_text = album_artist + ' ' + album_info.get('title', '')
    links = {
        'yandex': f"https://music.yandex.ru/search?text={urllib.parse.quote(search_text)}",
        'youtube_music': f"https://music.youtube.com/search?q={urllib.parse.quote(search_text)}",
        'youtube': f"https://www.youtube.com/results?search_query={urllib.parse.quote(search_text)}+album",
        'deezer': album_info.get('link', '')
    }
    
    for platform in ['yandex', 'youtube_music', 'youtube', 'deezer']:
        if platform in links and links[platform]:
            platform_buttons.append(InlineKeyboardButton(
                f"{platform_emoji.get(platform, '▶️')} {platform_names.get(platform, platform)}",
                url=links[platform]
            ))
    
    for i in range(0, len(platform_buttons), 2):
        if i + 1 < len(platform_buttons):
            keyboard.row(platform_buttons[i], platform_buttons[i + 1])
        else:
            keyboard.row(platform_buttons[i])
    
    encoded_artist = encode_callback_data(album_artist)
    keyboard.row(
        InlineKeyboardButton("🎤 Био", callback_data=f"bio_album_{encoded_artist}"),
        InlineKeyboardButton("🔙 Назад к альбомам", callback_data=f"albums_back_{encoded_artist}")
    )
    
    concert_info = check_concerts_yandex_music(album_artist)
    encoded_name = urllib.parse.quote(album_artist)
    keyboard.row(
        InlineKeyboardButton(
            f"🎫 {concert_info['message']}",
            callback_data=f"show_concerts_{encoded_name}"
        )
    )
    
    cover_url = album_info.get('cover_xl') or album_info.get('cover_big') or album_info.get('cover_medium')
    if cover_url:
        try:
            cover_response = requests.get(cover_url, timeout=15)
            if cover_response.status_code == 200:
                bot.send_photo(
                    message.chat.id,
                    photo=cover_response.content,
                    caption=text,
                    parse_mode='HTML',
                    reply_markup=keyboard
                )
                return
        except Exception as e:
            logger.error(f"Ошибка отправки обложки: {e}")
    
    bot.send_message(
        message.chat.id,
        text,
        parse_mode='HTML',
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

def send_album_result(message: Message, album_info: Dict[str, Any]):
    album_artist = album_info['artist']
    encoded_artist = encode_callback_data(album_artist)
    
    album_text = (
        f"💿 <b>{album_artist} — {album_info['title']}</b>\n\n"
        f"📅 <b>Год:</b> {album_info.get('year', 'Неизвестно')}\n"
    )
    
    if album_info.get('release_date'):
        formatted = format_release_date(album_info['release_date'])
        if formatted:
            album_text += f"📆 <b>Дата релиза:</b> {formatted}"
            relative_time = get_relative_time(album_info['release_date'])
            if relative_time:
                album_text += f"  <i>({relative_time})</i>"
            album_text += "\n"
    
    album_text += f"🎵 <b>Треков:</b> {album_info.get('track_count', 0)}\n\n"
    album_text += f"📋 <b>ТРЕКЛИСТ:</b>\n\n"
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    album_tracks = album_info.get('tracks', [])
    
    if album_tracks:
        for i, track in enumerate(album_tracks[:20], 1):
            title = track.get('title', 'Без названия')
            duration = track.get('duration', 0)
            minutes = duration // 60
            seconds = duration % 60
            duration_str = f"{minutes}:{seconds:02d}"
            track_id = track.get('id')
            
            track_artist = track.get('artist', album_artist)
            if isinstance(track_artist, dict):
                track_artist = track_artist.get('name', album_artist)
            
            if track_artist.lower() != album_artist.lower():
                album_text += f"{i}. <b>{track_artist}</b> — {title} ⏱ {duration_str} 🤝\n"
            else:
                album_text += f"{i}. <b>{track_artist}</b> — {title} ⏱ {duration_str}\n"
            
            if track_id:
                play_callback = generate_short_callback('play', track_id, track_artist, title)
                full_track_callback = f"full_track_{track_id}"
                
                keyboard.row(
                    InlineKeyboardButton(f"🎧 30 сек", callback_data=play_callback),
                    InlineKeyboardButton(f"🎵 Полный — {title[:15]}", callback_data=full_track_callback)
                )
    else:
        album_text += "❌ Не удалось загрузить список треков"
    
    if len(album_tracks) > 20:
        album_text += f"\n... и еще {len(album_tracks) - 20} треков"
    
    album_text += f"\n\n🎧 <b>Слушать на платформах:</b>"
    
    platform_buttons = []
    platform_emoji = {
        'yandex': '🎵',
        'youtube_music': '▶️',
        'youtube': '📺',
        'deezer': '🎧'
    }
    platform_names = {
        'yandex': 'Яндекс.Музыка',
        'youtube_music': 'YouTube Music',
        'youtube': 'YouTube',
        'deezer': 'Deezer'
    }
    
    search_text = album_artist + ' ' + album_info['title']
    links = {
        'yandex': f"https://music.yandex.ru/search?text={urllib.parse.quote(search_text)}",
        'youtube_music': f"https://music.youtube.com/search?q={urllib.parse.quote(search_text)}",
        'youtube': f"https://www.youtube.com/results?search_query={urllib.parse.quote(search_text)}+album",
        'deezer': album_info['link']
    }
    
    for platform in ['yandex', 'youtube_music', 'youtube', 'deezer']:
        if platform in links:
            platform_buttons.append(InlineKeyboardButton(
                f"{platform_emoji.get(platform, '▶️')} {platform_names.get(platform, platform)}",
                url=links[platform]
            ))
    
    for i in range(0, len(platform_buttons), 2):
        if i + 1 < len(platform_buttons):
            keyboard.row(platform_buttons[i], platform_buttons[i + 1])
        else:
            keyboard.row(platform_buttons[i])
    
    track_id = album_info.get('id', 0)
    bio_callback = generate_short_callback('bio', track_id, album_artist, album_info['title'])
    fav_callback = generate_short_callback('fav', track_id, album_artist, album_info['title'])
    
    keyboard.row(
        InlineKeyboardButton("🎤 Био", callback_data=bio_callback),
        InlineKeyboardButton("⭐ Избранное", callback_data=fav_callback),
        InlineKeyboardButton(
            "🔍 Все платформы",
            url=f"https://www.google.com/search?q={urllib.parse.quote(search_text)}"
        )
    )
    
    concert_info = check_concerts_yandex_music(album_artist)
    encoded_name = urllib.parse.quote(album_artist)
    keyboard.row(
        InlineKeyboardButton(
            f"🎫 {concert_info['message']}",
            callback_data=f"show_concerts_{encoded_name}"
        )
    )
    
    if album_info.get('cover_url'):
        try:
            cover_response = requests.get(album_info['cover_url'], timeout=15)
            if cover_response.status_code == 200:
                bot.send_photo(
                    message.chat.id,
                    photo=cover_response.content,
                    caption=album_text,
                    parse_mode='HTML',
                    reply_markup=keyboard
                )
                return
        except Exception as e:
            logger.error(f"Ошибка отправки обложки альбома: {e}")
    
    bot.send_message(
        message.chat.id,
        album_text,
        parse_mode='HTML',
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

def send_all_tracks(message: Message, artist_name: str):
    bot.send_chat_action(message.chat.id, 'typing')
    
    all_tracks = get_all_artist_tracks(artist_name, limit=200)
    
    if not all_tracks:
        bot.reply_to(
            message,
            f"❌ Не удалось найти треки исполнителя: {artist_name}",
            parse_mode='HTML'
        )
        return
    
    all_tracks.sort(key=lambda x: x.get('rank', 0), reverse=True)
    
    text = f"🎵 <b>ВСЕ ТРЕКИ: {artist_name}</b>\n\n"
    text += f"📊 <b>Всего найдено:</b> {len(all_tracks)} треков\n\n"
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    for i, track in enumerate(all_tracks[:20], 1):
        title = track.get('title', 'Без названия')
        duration = track.get('duration', 0)
        minutes = duration // 60
        seconds = duration % 60
        duration_str = f"{minutes}:{seconds:02d}"
        track_id = track.get('id')
        
        text += f"{i}. <b>{artist_name}</b> — {title} ⏱ {duration_str}\n"
        
        if track_id:
            play_callback = generate_short_callback('play', track_id, artist_name, title)
            try:
                keyboard.add(InlineKeyboardButton(
                    f"▶️ {title[:25]}",
                    callback_data=play_callback
                ))
            except Exception as e:
                logger.warning(f"Не удалось создать кнопку для трека {title}: {e}")
    
    if len(all_tracks) > 20:
        text += f"\n... и еще {len(all_tracks) - 20} треков"
    
    concert_info = check_concerts_yandex_music(artist_name)
    encoded_name = urllib.parse.quote(artist_name)
    
    keyboard.row(
        InlineKeyboardButton(
            f"🎫 {concert_info['message']}",
            callback_data=f"show_concerts_{encoded_name}"
        ),
        InlineKeyboardButton(
            "▶️ YouTube Music",
            url=f"https://music.youtube.com/search?q={urllib.parse.quote(artist_name)}"
        )
    )
    
    bot.send_message(
        message.chat.id,
        text,
        parse_mode='HTML',
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

# === ОБНОВЛЁННАЯ ФУНКЦИЯ ДЛЯ ОТПРАВКИ ТРЕКА ===
def send_track_result(message: Message, track_info: Dict[str, Any]):
    ai_fact = generate_ai_fact(track_info['main_artist'], track_info['title'])
    song_meaning = get_song_meaning(track_info['title'], track_info['main_artist'])
    
    artist_name = track_info['main_artist']
    
    # ===== ПРОВЕРЯЕМ ПРЕДСТОЯЩИЙ РЕЛИЗ =====
    upcoming_release = get_upcoming_release(artist_name)
    
    track_text = (
        f"🎵 <b>{track_info['artists']} — {track_info['title']}</b>\n\n"
        f"💿 <b>Альбом:</b> {track_info['album']}"
    )
    
    if track_info.get('year'):
        track_text += f" ({track_info['year']})"
    
    if track_info.get('formatted_date'):
        formatted_date = track_info['formatted_date']
        track_text += f"\n📆 <b>Дата релиза:</b> {formatted_date}"
        
        release_date = track_info.get('release_date')
        if release_date:
            relative_time = get_relative_time(release_date)
            if relative_time:
                track_text += f"  <i>({relative_time})</i>"
        
    elif track_info.get('release_date'):
        formatted = format_release_date(track_info['release_date'])
        if formatted:
            track_text += f"\n📆 <b>Дата релиза:</b> {formatted}"
            relative_time = get_relative_time(track_info['release_date'])
            if relative_time:
                track_text += f"  <i>({relative_time})</i>"
    else:
        track_text += f"\n📆 <b>Дата релиза:</b> неизвестна"
    
    track_text += f"\n⏱ <b>Длительность:</b> {track_info['duration_str']}"
    
    if track_info.get('explicit'):
        track_text += "\n🔞 <b>Parental Advisory — Explicit Content</b>"
    
    if song_meaning:
        track_text += f"\n\n📖 <b>Смысл песни:</b>\n{song_meaning['meaning']}"
        if song_meaning.get('emotion'):
            track_text += f"\n\n🎭 <b>Настроение:</b> {song_meaning['emotion']}"
    else:
        track_text += f"\n\n🤖 <b>ИИ-факт:</b>\n{ai_fact}"
    
    # ===== ДОБАВЛЯЕМ ИНФОРМАЦИЮ О ПРЕДСТОЯЩЕМ РЕЛИЗЕ =====
    if upcoming_release and upcoming_release.get('has_upcoming'):
        days = upcoming_release.get('days_left', 0)
        
        if days == 0:
            date_text = "СЕГОДНЯ! 🎉"
        elif days == 1:
            date_text = "ЗАВТРА! 🔥"
        else:
            date_text = f"через {days} дней"
        
        track_text += f"\n\n🎉 <b>НОВЫЙ РЕЛИЗ У {artist_name.upper()}!</b>\n"
        track_text += f"💿 <b>{upcoming_release.get('release_title', 'Новый альбом')}</b>\n"
        track_text += f"📅 <b>Выходит:</b> {date_text}"
        
        if upcoming_release.get('release_date'):
            formatted = format_release_date(upcoming_release['release_date'])
            if formatted:
                track_text += f"  <i>({formatted})</i>"
    
    track_text += f"\n\n🎧 <b>Слушать на платформах:</b>"
    
    # ===== КЛАВИАТУРА =====
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    # ===== ПЛАТФОРМЫ (БЕЗ APPLE MUSIC) =====
    platform_buttons = []
    platform_emoji = {
        'yandex': '🎵',
        'youtube_music': '▶️',
        'youtube': '📺',
        'deezer': '🎧'
    }
    platform_names = {
        'yandex': 'Яндекс.Музыка',
        'youtube_music': 'YouTube Music',
        'youtube': 'YouTube',
        'deezer': 'Deezer'
    }
    platform_urls = {
        'yandex': track_info['links'].get('yandex', ''),
        'youtube_music': track_info['links'].get('youtube_music', ''),
        'youtube': track_info['links'].get('youtube', ''),
        'deezer': track_info['links'].get('deezer', '')
    }
    
    # Добавляем платформы
    for platform in ['yandex', 'youtube_music', 'youtube', 'deezer']:
        if platform_urls.get(platform):
            platform_buttons.append(InlineKeyboardButton(
                f"{platform_emoji.get(platform, '▶️')} {platform_names.get(platform, platform)}",
                url=platform_urls[platform]
            ))
    
    # Выводим кнопки платформ по 2 в ряд
    for i in range(0, len(platform_buttons), 2):
        if i + 1 < len(platform_buttons):
            keyboard.row(platform_buttons[i], platform_buttons[i + 1])
        else:
            keyboard.row(platform_buttons[i])
    
    # ===== ВТОРОЙ РЯД: 30 сек, Полный трек, Био =====
    track_id = track_info['track_id']
    track_title = track_info['title']
    
    play_callback = generate_short_callback('play', track_id, artist_name, track_title)
    bio_callback = generate_short_callback('bio', track_id, artist_name, track_title)
    release_callback = generate_short_callback('release', track_id, artist_name, track_title)
    fav_callback = generate_short_callback('fav', track_id, artist_name, track_title)
    
    keyboard.row(
        InlineKeyboardButton("🎧 30 сек", callback_data=play_callback),
        InlineKeyboardButton("🎵 Полный трек", callback_data=f"full_track_{track_id}"),
        InlineKeyboardButton("🎤 Био", callback_data=bio_callback)
    )
    
    # ===== ТРЕТИЙ РЯД: Релиз, Избранное, Все платформы =====
    keyboard.row(
        InlineKeyboardButton("📆 Релиз", callback_data=release_callback),
        InlineKeyboardButton("⭐ Избранное", callback_data=fav_callback),
        InlineKeyboardButton(
            "🔍 Все платформы",
            url=f"https://www.google.com/search?q={urllib.parse.quote(artist_name + ' ' + track_title + ' music')}"
        )
    )
    
    # ===== ЧЕТВЁРТЫЙ РЯД: Концерты =====
    concert_info = check_concerts_yandex_music(artist_name)
    encoded_name = urllib.parse.quote(artist_name)
    
    if concert_info['has_concerts']:
        track_text += f"\n\n🎤 <b>У {artist_name} есть концерты!</b>"
    
    keyboard.row(
        InlineKeyboardButton(
            f"🎫 {concert_info['message']}",
            callback_data=f"show_concerts_{encoded_name}"
        )
    )
    
    # ===== СОХРАНЯЕМ В КЭШ =====
    user_track_cache[track_id] = track_info
    
    # ===== ОТПРАВЛЯЕМ =====
    cover_data = get_cover_data(track_info)
    
    try:
        if cover_data:
            bot.send_photo(
                message.chat.id,
                photo=cover_data,
                caption=track_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return
        
        bot.send_message(
            message.chat.id,
            track_text,
            parse_mode='HTML',
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")
        
        if "BUTTON_DATA_INVALID" in str(e) or "BUTTON_DA" in str(e):
            logger.warning("⚠️ Проблема с callback_data, отправляем упрощенное сообщение...")
            
            simple_keyboard = InlineKeyboardMarkup(row_width=1)
            for platform in ['yandex', 'youtube_music', 'youtube', 'deezer']:
                if platform_urls.get(platform):
                    simple_keyboard.add(InlineKeyboardButton(
                        f"▶️ {platform_names.get(platform, platform)}",
                        url=platform_urls[platform]
                    ))
            
            bot.send_message(
                message.chat.id,
                track_text + "\n\n⚠️ Кнопки управления временно недоступны\n🔗 Используйте ссылки ниже",
                parse_mode='HTML',
                reply_markup=simple_keyboard,
                disable_web_page_preview=True
            )
            
# === ОСТАЛЬНЫЕ ФУНКЦИИ ===
def generate_ai_fact(artist_name: str, track_name: str = None) -> str:
    artist_lower = artist_name.lower()
    
    for key, facts in AI_FACTS_DATABASE.items():
        if key in artist_lower or artist_lower in key:
            return random.choice(facts)
    
    templates = [
        f"🎤 {artist_name} — один из самых ярких исполнителей года!",
        f"🔥 Треки {artist_name} набирают миллионы прослушиваний",
        f"⭐ Подпишись на {artist_name}, чтобы не пропустить новые релизы!",
    ]
    if track_name:
        templates.append(f"🎧 «{track_name}» — в топе этой недели!")
    
    return random.choice(templates)

def search_track_with_retry(query: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
    for attempt in range(max_retries):
        try:
            logger.info(f"Поиск трека (попытка {attempt + 1}): {query}")
            result = search_track_full(query)
            if result:
                return result
        except Exception as e:
            logger.warning(f"Ошибка при поиске (попытка {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(RETRY_DELAY)
    return None

def search_album_with_retry(query: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
    for attempt in range(max_retries):
        try:
            logger.info(f"Поиск альбома (попытка {attempt + 1}): {query}")
            result = search_album_full(query)
            if result:
                return result
        except Exception as e:
            logger.warning(f"Ошибка при поиске альбома (попытка {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(RETRY_DELAY)
    return None

def get_search_suggestions(query: str) -> str:
    try:
        parts = query.split()
        if len(parts) > 1:
            track_name = ' '.join(parts[:-1])
            url = f"https://api.deezer.com/search?q={urllib.parse.quote(track_name)}&limit=3"
            response = requests.get(url, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('data'):
                    suggestions = []
                    for track in data['data'][:3]:
                        title = track.get('title', '')
                        artist = track['artist']['name']
                        suggestions.append(f"• {title} — {artist}")
                    
                    if suggestions:
                        return '\n'.join(suggestions)
        
        return ""
    except:
        return ""

def set_bot_commands():
    commands = [
        BotCommand("start", "Главное меню"),
        BotCommand("search", "Поиск трека"),
        BotCommand("album", "Поиск альбома"),
        BotCommand("albums", "Все альбомы исполнителя"),
        BotCommand("alltracks", "Все треки исполнителя"),
        BotCommand("concerts", "Концерты в Яндекс Музыке"),
        BotCommand("bio", "Биография исполнителя"),
        BotCommand("hit", "Популярные треки"),
        BotCommand("new", "Новинки музыки"),
        BotCommand("sad", "Грустная музыка"),
        BotCommand("happy", "Весёлая музыка"),
        BotCommand("energy", "Энергичная музыка"),
        BotCommand("relax", "Спокойная музыка"),
        BotCommand("romantic", "Романтичная музыка"),
        BotCommand("focus", "Музыка для концентрации"),
        BotCommand("subscribe", "Подписаться на исполнителя"),
        BotCommand("unsubscribe", "Отписаться от исполнителя"),
        BotCommand("subscriptions", "Мои подписки"),
        BotCommand("checkreleases", "Проверить новые релизы"),
        BotCommand("help", "Помощь")
    ]

    
    for attempt in range(MAX_RETRIES):
        try:
            bot.set_my_commands(commands)
            logger.info("✅ Команды меню установлены")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Ошибка установки команд (попытка {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
    
    logger.error("❌ Не удалось установить команды меню после всех попыток")
    return False

# === ОБРАБОТЧИКИ КОМАНД ===
@bot.message_handler(commands=['start'])
def send_welcome(message: Message):
    welcome_text = (
        "🎵 <b>LE MONDE MUSIC</b>\n"
        "🤖 Музыкальный бот\n"
        "🎧 С 30-секундным превью КАЖДОГО трека\n"
        "🎵 С ПОЛНЫМ ПРОСЛУШИВАНИЕМ ТРЕКОВ\n"
        "📆 С датой релиза и временем с момента выхода\n"
        "📖 Со смыслом песен\n"
        "🎤 С биографией из Deezer\n"
        "💿 С альбомами и ▶️ для каждого трека\n"
        "🎫 С концертами через Яндекс Музыку\n"
        "🖼 АВТОМАТИЧЕСКАЯ ГЕНЕРАЦИЯ ОБЛОЖЕК\n"
        "🔍 ИЩЕТ В 4-Х ИСТОЧНИКАХ:\n"
        "   • Deezer\n"
        "   • Яндекс Музыка\n"
        "   • YouTube Music\n"
        "   • YouTube\n"
        "🔍 НАХОДИТ ВСЕ ТРЕКИ И АЛЬБОМЫ!\n"
        "🔢 ПОДДЕРЖИВАЕТ ПОИСК ПО ЧИСЛАМ (911, 21, 7 rings и т.д.)\n\n"
        "🔍 <b>Поиск:</b>\n"
        "/search <название> — поиск трека\n"
        "/album <название> — поиск альбома\n"
        "/albums <исполнитель> — все альбомы\n"
        "/alltracks <исполнитель> — все треки\n"
        "/concerts <исполнитель> — концерты\n"
        "/bio <исполнитель> — биография\n\n"
        "📱 <b>Открыть Mini App:</b>"
    )
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(
        "📱 Открыть Mini App",
        web_app=WebAppInfo(url="https://antog1439-afk.github.io/Muzyka/")
    ))
    bot.reply_to(message, welcome_text, parse_mode='HTML', reply_markup=markup)

@bot.message_handler(commands=['help'])
def help_command(message: Message):
    help_text = (
        "🎵 <b>Помощь по командам</b>\n\n"
        "🔍 <b>Поиск:</b>\n"
        "• /search <название> — поиск трека\n"
        "• /album <название> — поиск альбома\n"
        "• /albums <исполнитель> — все альбомы\n"
        "• /alltracks <исполнитель> — все треки\n"
        "• /concerts <исполнитель> — концерты\n"
        "• /bio <исполнитель> — биография\n"
        "• Просто напиши название — бот сам определит\n\n"
        "🔥 <b>Быстрый поиск по настроению:</b>\n"
        "• /hit — Популярные треки\n"
        "• /new — Новинки музыки\n"
        "• /sad — Грустная музыка\n"
        "• /happy — Весёлая музыка\n"
        "• /energy — Энергичная музыка\n"
        "• /relax — Спокойная музыка\n"
        "• /romantic — Романтичная музыка\n"
        "• /focus — Музыка для концентрации\n\n"
        "🎵 <b>Прослушивание:</b>\n"
        "• 🎧 30 сек — короткое превью\n"
        "• 🎵 Полный трек — полная версия (скачивается с YouTube)\n\n"
        "🔔 <b>Подписки:</b>\n"
        "• /subscribe <имя> — подписаться\n"
        "• /unsubscribe <имя> — отписаться\n"
        "• /subscriptions — список подписок\n\n"
        "🎵 <b>LE MONDE MUSIC</b>"
    )
    bot.reply_to(message, help_text, parse_mode='HTML')

@bot.message_handler(commands=['search'])
def search_command(message: Message):
    query = message.text.replace('/search', '', 1).strip()
    
    if not query:
        bot.reply_to(message, "Введите название трека после команды.\n\nПример: /search 911", parse_mode='HTML')
        return
    
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        status_msg = bot.reply_to(message, f"🔍 Ищем трек: {query} (в 4-х источниках)...")
        
        # ===== НОВАЯ ЛОГИКА =====
        tracks = search_tracks_by_title(query)
        
        if tracks:
            bot.delete_message(message.chat.id, status_msg.message_id)
            
            if len(tracks) == 1:
                # Только один трек — сразу показываем
                send_track_result(message, parse_track_data(tracks[0]))
            else:
                # Несколько треков — показываем список
                send_track_selection(message, query, tracks)
        else:
            bot.delete_message(message.chat.id, status_msg.message_id)
            
            suggestion = get_search_suggestions(query)
            reply_text = f"❌ Не найден трек: {query}\n\n"
            
            if suggestion:
                reply_text += f"💡 Возможно, вы искали:\n{suggestion}\n\n"
            
            reply_text += "💡 Попробуйте:\n"
            reply_text += "• /search <трек> <исполнитель>\n"
            reply_text += "• /albums <исполнитель> — все альбомы\n"
            reply_text += "• /alltracks <исполнитель> — все треки"
            
            bot.reply_to(message, reply_text, parse_mode='HTML')
            
    except Exception as e:
        logger.error(f"Ошибка в search_command: {e}")
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")

@bot.message_handler(commands=['album'])
def album_command(message: Message):
    query = message.text.replace('/album', '', 1).strip()
    
    if not query:
        bot.reply_to(message, "Введите название альбома после команды.\n\nПример: /album 21", parse_mode='HTML')
        return
    
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        status_msg = bot.reply_to(message, f"🔍 Ищем альбом: {query} (в 4-х источниках)...")
        
        album_info = search_album_with_retry(query)
        
        if album_info:
            try:
                bot.delete_message(message.chat.id, status_msg.message_id)
            except:
                pass
            send_album_result(message, album_info)
        else:
            try:
                bot.delete_message(message.chat.id, status_msg.message_id)
            except:
                pass
            bot.reply_to(
                message, 
                f"❌ Не найден альбом: {query}\n\n"
                f"💡 Попробуйте:\n"
                f"• Уточнить название\n"
                f"• Использовать /search <трек>\n"
                f"• Использовать /albums <исполнитель>"
            )
    except Exception as e:
        logger.error(f"Ошибка в album_command: {e}")
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")

@bot.message_handler(commands=['albums'])
def albums_command(message: Message):
    query = message.text.replace('/albums', '', 1).strip()
    
    if not query:
        bot.reply_to(message, "Введите имя исполнителя.\n\nПример: /albums Асия", parse_mode='HTML')
        return
    
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        send_artist_albums(message, query)
        
    except Exception as e:
        logger.error(f"Ошибка в albums_command: {e}")
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")

@bot.message_handler(commands=['alltracks'])
def all_tracks_command(message: Message):
    query = message.text.replace('/alltracks', '', 1).strip()
    
    if not query:
        bot.reply_to(message, "Введите имя исполнителя.\n\nПример: /alltracks Асия", parse_mode='HTML')
        return
    
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        send_all_tracks(message, query)
        
    except Exception as e:
        logger.error(f"Ошибка в alltracks_command: {e}")
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")

@bot.message_handler(commands=['concerts'])
def concerts_command(message: Message):
    query = message.text.replace('/concerts', '', 1).strip()
    
    if not query:
        bot.reply_to(
            message,
            "🎤 Введите имя исполнителя\n\nПример: /concerts Асия",
            parse_mode='HTML'
        )
        return
    
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        
        if hasattr(message, 'message_id'):
            status_msg = bot.reply_to(message, "🔍 Ищем концерты...")
        
        concert_data = get_cached_concerts(query)
        
        if 'status_msg' in locals() and status_msg and hasattr(status_msg, 'message_id'):
            try:
                bot.delete_message(message.chat.id, status_msg.message_id)
            except:
                pass
        
        keyboard = InlineKeyboardMarkup(row_width=2)
        encoded_name = urllib.parse.quote(query)
        
        keyboard.add(InlineKeyboardButton(
            "🎵 Яндекс Музыка",
            url=f"https://music.yandex.ru/artist/{encoded_name}?tab=concerts"
        ))
        
        keyboard.add(InlineKeyboardButton(
            "🎫 Яндекс Афиша",
            url=f"https://afisha.yandex.ru/search?text={encoded_name}"
        ))
        
        keyboard.add(InlineKeyboardButton(
            "🎤 Биография",
            callback_data=f"bio_concert_{encoded_name}"
        ))
        
        if concert_data['concerts']:
            bot.send_message(
                message.chat.id,
                concert_data['formatted_text'],
                parse_mode='HTML',
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        else:
            text = f"🎤 <b>{query.upper()}</b>\n\n"
            text += "❌ Концерты не найдены\n\n"
            text += "💡 Возможные причины:\n"
            text += "• Концерты ещё не анонсированы\n"
            text += "• Исполнитель не гастролирует\n"
            text += "• Ошибка в написании имени\n\n"
            text += "🔍 Попробуйте поискать на Яндекс Афише"
            
            bot.send_message(
                message.chat.id,
                text,
                parse_mode='HTML',
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        
    except Exception as e:
        logger.error(f"Ошибка в concerts_command: {e}")
        bot.reply_to(
            message,
            f"❌ Ошибка при поиске концертов: {str(e)[:100]}",
            parse_mode='HTML'
        )

@bot.message_handler(commands=['bio'])
def bio_command(message: Message):
    query = message.text.replace('/bio', '', 1).strip()
    
    if not query:
        bot.reply_to(message, "Введите имя исполнителя после команды.\n\nПример: /bio Асия", parse_mode='HTML')
        return
    
    send_artist_bio(message, query)

# === ОСТАЛЬНЫЕ ОБРАБОТЧИКИ ===
@bot.message_handler(commands=['hit', 'new', 'sad', 'happy', 'energy', 'relax', 'romantic', 'focus'])
def quick_search_command(message: Message):
    command = message.text.replace('/', '').strip().lower()
    
    mood_map = {
        'hit': 'популярная музыка',
        'new': 'новинки музыки',
        'sad': 'грустная музыка',
        'happy': 'веселая музыка',
        'energy': 'энергичная музыка',
        'relax': 'спокойная музыка',
        'romantic': 'романтичная музыка',
        'focus': 'музыка для концентрации'
    }
    
    mood_names = {
        'hit': '🔥 Популярные треки',
        'new': '🆕 Новинки музыки',
        'sad': '😢 Грустная музыка',
        'happy': '😊 Весёлая музыка',
        'energy': '⚡ Энергичная музыка',
        'relax': '😌 Спокойная музыка',
        'romantic': '💖 Романтичная музыка',
        'focus': '📚 Музыка для концентрации'
    }
    
    query = mood_map.get(command, 'популярная музыка')
    mood_name = mood_names.get(command, '🎵 Музыка')
    
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        track_info = search_track_with_retry(query)
        
        if track_info:
            send_track_result(message, track_info)
        else:
            bot.reply_to(message, f"Не удалось найти трек для настроения: {mood_name}")
    except Exception as e:
        logger.error(f"Ошибка в quick_search_command: {e}")
        bot.reply_to(message, f"Ошибка: {str(e)[:100]}")

# === ПОДПИСКИ ===
@bot.message_handler(commands=['subscribe'])
def subscribe_command(message: Message):
    args = message.text.replace('/subscribe', '', 1).strip()
    if not args:
        bot.reply_to(message, "Укажите имя исполнителя.\n\nПример: /subscribe Асия", parse_mode='HTML')
        return
    
    artist_name = args
    user_id = str(message.from_user.id)
    
    if user_id not in user_subscriptions:
        user_subscriptions[user_id] = []
    
    if any(a['name'].lower() == artist_name.lower() for a in user_subscriptions[user_id]):
        bot.reply_to(message, f"Вы уже подписаны на {artist_name}")
        return
    
    user_subscriptions[user_id].append({'name': artist_name})
    try:
        with open(SUBSCRIPTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_subscriptions, f, ensure_ascii=False, indent=2)
        bot.reply_to(message, f"🔔 Вы подписались на {artist_name}")
    except Exception as e:
        logger.error(f"Ошибка сохранения подписки: {e}")
        bot.reply_to(message, "Ошибка при сохранении подписки")

@bot.message_handler(commands=['unsubscribe'])
def unsubscribe_command(message: Message):
    args = message.text.replace('/unsubscribe', '', 1).strip()
    if not args:
        bot.reply_to(message, "Укажите имя исполнителя.\n\nПример: /unsubscribe Асия", parse_mode='HTML')
        return
    
    artist_name = args
    user_id = str(message.from_user.id)
    
    if user_id in user_subscriptions:
        original_len = len(user_subscriptions[user_id])
        user_subscriptions[user_id] = [a for a in user_subscriptions[user_id] if a['name'].lower() != artist_name.lower()]
        
        if len(user_subscriptions[user_id]) < original_len:
            try:
                with open(SUBSCRIPTIONS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(user_subscriptions, f, ensure_ascii=False, indent=2)
                bot.reply_to(message, f"❌ Вы отписались от {artist_name}")
            except Exception as e:
                logger.error(f"Ошибка сохранения: {e}")
                bot.reply_to(message, "Ошибка при сохранении")
        else:
            bot.reply_to(message, f"❌ Вы не были подписаны на {artist_name}")
    else:
        bot.reply_to(message, f"❌ У вас нет активных подписок")

@bot.message_handler(commands=['subscriptions'])
def list_subscriptions_command(message: Message):
    user_id = str(message.from_user.id)
    
    if user_id not in user_subscriptions or not user_subscriptions[user_id]:
        bot.reply_to(message, "📭 У вас нет активных подписок.\n\nИспользуйте /subscribe Асия, чтобы подписаться", parse_mode='HTML')
        return
    
    artists = [a['name'] for a in user_subscriptions[user_id]]
    artists_list = '\n'.join([f"🎤 {a}" for a in artists])
    
    bot.reply_to(message, f"📋 <b>Ваши подписки:</b>\n\n{artists_list}\n\nВсего: {len(artists)} исполнителей", parse_mode='HTML')

# === ОСНОВНОЙ ОБРАБОТЧИК ТЕКСТА ===
@bot.message_handler(func=lambda message: True)
def handle_message(message: Message):
    """Основной обработчик текстовых сообщений"""
    
    # Если это команда — пропускаем (обрабатывается другими обработчиками)
    if message.text.startswith('/'):
        return
    
    query = message.text.strip()
    
    if len(query) < 1:
        bot.reply_to(message, "❌ Слишком короткий запрос (минимум 1 символ)")
        return
    
    # ===== ПРОВЕРЯЕМ, НЕ ЗАПРОС ЛИ ЭТО БИОГРАФИИ =====
    bio_keywords = ['биография', 'био', 'кто такой', 'кто такая', 'расскажи о', 'информация о']
    is_bio_request = any(keyword in query.lower() for keyword in bio_keywords)
    
    if is_bio_request:
        clean_query = query
        for word in bio_keywords:
            clean_query = clean_query.replace(word, '').strip()
        if clean_query:
            send_artist_bio(message, clean_query)
            return
    
    # ===== ПРОВЕРЯЕМ, НЕ ЗАПРОС ЛИ ЭТО АЛЬБОМА =====
    album_keywords = ['альбом', 'album', 'сборник', 'пластинка']
    is_album_search = any(keyword in query.lower() for keyword in album_keywords)
    
    if is_album_search:
        clean_query = query
        for word in album_keywords:
            clean_query = clean_query.replace(word, '').strip()
        if clean_query:
            album_info = search_album_with_retry(clean_query)
            if album_info:
                send_album_result(message, album_info)
                return
    
    # ===== ОСНОВНОЙ ПОИСК ТРЕКОВ (НОВАЯ ЛОГИКА) =====
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        
        # 🔥 НОВОЕ: ищем ВСЕ треки с похожим названием
        tracks = search_tracks_by_title(query)
        
        if tracks:
            if len(tracks) == 1:
                # Только один трек — сразу показываем
                send_track_result(message, parse_track_data(tracks[0]))
            else:
                # Несколько треков — показываем список для выбора
                send_track_selection(message, query, tracks)
            return
        
        # ===== ЕСЛИ ТРЕКИ НЕ НАЙДЕНЫ — ПРОВЕРЯЕМ АЛЬБОМЫ =====
        album_info = search_album_with_retry(query)
        if album_info:
            send_album_result(message, album_info)
            return
        
        # ===== НИЧЕГО НЕ НАШЛИ =====
        bot.reply_to(
            message,
            f"🔍 Не найдено: {query}\n\n"
            f"💡 Попробуйте:\n"
            f"• Уточнить название\n"
            f"• Добавить исполнителя\n"
            f"• Использовать /search <трек>\n"
            f"• Использовать /album <альбом>\n"
            f"• Использовать /albums <исполнитель>\n"
            f"• Использовать /bio <исполнитель>"
        )
        
    except Exception as e:
        logger.error(f"Ошибка в handle_message: {e}")
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")

# === ОБРАБОТЧИК CALLBACK ===
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        logger.info(f"📩 Получен callback: {call.data}")

        # ============================================================
        # === ОБРАБОТЧИК ДЛЯ ft_ (короткая ссылка на полный трек) ===
        # ============================================================
        if call.data.startswith('ft_'):
            track_id = int(call.data.replace('ft_', ''))
            # Меняем данные call на полный формат
            call.data = f"full_track_{track_id}"
            # Продолжаем выполнение (не возвращаем, чтобы обработалось дальше)

        # === НОВЫЙ ОБРАБОТЧИК ДЛЯ ПОИСКА ПО ИСПОЛНИТЕЛЮ ===
        if call.data.startswith('search_artist_'):
            artist_name = urllib.parse.unquote(call.data.replace('search_artist_', ''))
            bot.answer_callback_query(call.id, f"🔍 Ищем треки {artist_name}...")
            
            class FakeMessage:
                def __init__(self, chat_id, text):
                    self.chat = type('obj', (object,), {'id': chat_id})
                    self.text = text
            
            fake_msg = FakeMessage(call.message.chat.id, artist_name)
            handle_message(fake_msg)
            return

        if call.data.startswith('bio_from_release_'):
            artist_name = urllib.parse.unquote(call.data.replace('bio_from_release_', ''))
            bot.answer_callback_query(call.id, "🎤 Загружаем биографию...")
            send_artist_bio(call.message, artist_name)
            return
        
        if call.data.startswith('show_concerts_'):
            artist_name = call.data.replace('show_concerts_', '')
            artist_name = urllib.parse.unquote(artist_name)
            
            class FakeMessage:
                def __init__(self, chat_id, text):
                    self.chat = type('obj', (object,), {'id': chat_id})
                    self.text = text
                    self.reply_to = None
            
            fake_msg = FakeMessage(call.message.chat.id, f"/concerts {artist_name}")
            concerts_command(fake_msg)
            bot.answer_callback_query(call.id, f"🎫 Концерты {artist_name}")
            return

        # === ОБРАБОТЧИК ВЫБОРА ТРЕКА ===
        if call.data.startswith('select_track_'):
            try:
                track_id = int(call.data.replace('select_track_', ''))
        
                # Пытаемся получить из кэша
                track_info = user_track_cache.get(track_id)
        
                if not track_info:
                    # Если нет в кэше — загружаем из Deezer
                    logger.info(f"🔍 Загружаем трек из Deezer: {track_id}")
                    url = f"https://api.deezer.com/track/{track_id}"
                    response = requests.get(url, timeout=15)
                    if response.status_code == 200:
                        track_data = response.json()
                        track_info = parse_track_data(track_data)
                    else:
                        bot.answer_callback_query(call.id, "❌ Трек не найден на Deezer", show_alert=True)
                        return
        
                if not track_info:
                    bot.answer_callback_query(call.id, "❌ Трек не найден", show_alert=True)
                    return
        
                # Удаляем сообщение с выбором
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
        
                # Отправляем трек с обложкой
                bot.answer_callback_query(call.id, f"✅ {track_info['title']} — {track_info['artists']}")
                send_track_result(call.message, track_info)
                return
        
            except Exception as e:
                logger.error(f"Ошибка выбора трека: {e}")
                bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)[:50]}", show_alert=True)
                return
        
        if call.data.startswith('bio_concert_'):
            artist_name = call.data.replace('bio_concert_', '')
            artist_name = urllib.parse.unquote(artist_name)
            bot.answer_callback_query(call.id, "🎤 Загружаем биографию...")
            send_artist_bio(call.message, artist_name)
            return
        
        if call.data.startswith('albums_page_'):
            parts = call.data.split('_')
            if len(parts) >= 3:
                artist_name = parts[2].replace('_', ' ')
                page = int(parts[3]) if len(parts) > 3 else 0
                send_artist_albums(call.message, artist_name, page)
                bot.answer_callback_query(call.id, f"📄 Страница {page + 1}")
                return
        
        if call.data.startswith('album_detail_'):
            parts = call.data.split('_')
            if len(parts) >= 3:
                album_id = int(parts[2])
                artist_name = parts[3].replace('_', ' ') if len(parts) > 3 else ''
                send_album_detail(call.message, album_id, artist_name)
                bot.answer_callback_query(call.id, "💿 Загрузка альбома...")
                return
        
        if call.data.startswith('albums_back_'):
            artist_name = call.data.replace('albums_back_', '').replace('_', ' ')
            send_artist_albums(call.message, artist_name)
            bot.answer_callback_query(call.id, "🔙 Возврат к альбомам")
            return
        
        if call.data.startswith('all_tracks_'):
            artist_name = call.data.replace('all_tracks_', '').replace('_', ' ')
            send_all_tracks(call.message, artist_name)
            bot.answer_callback_query(call.id, "✅ Загружаем все треки...")
            return
        
        if call.data.startswith('full_track_'):
            # Полная логика обработки полного трека
            try:
                track_id = int(call.data.replace('full_track_', ''))
                track_info = user_track_cache.get(track_id)
                
                if not track_info:
                    bot.answer_callback_query(call.id, "❌ Трек не найден", show_alert=True)
                    return
                
                if not YT_DLP_AVAILABLE:
                    bot.answer_callback_query(call.id, "❌ Функция недоступна. Установите yt-dlp", show_alert=True)
                    return
                
                bot.answer_callback_query(call.id, "⏳ Ищу трек на YouTube...")
                status_msg = bot.send_message(
                    call.message.chat.id,
                    f"🔍 Ищу полную версию трека:\n"
                    f"🎵 {track_info['artists']} — {track_info['title']}\n\n"
                    f"⏳ Это может занять 5-15 секунд..."
                )
                
                query = f"{track_info['main_artist']} {track_info['title']}"
                audio_data = download_full_track_from_youtube(query)
                
                try:
                    bot.delete_message(call.message.chat.id, status_msg.message_id)
                except:
                    pass
                
                if audio_data:
                    cover_data = get_cover_data(track_info)
                    
                    try:
                        if cover_data:
                            bot.send_audio(
                                call.message.chat.id,
                                audio=audio_data,
                                title=track_info['title'],
                                performer=track_info['main_artist'],
                                duration=track_info.get('duration', 0),
                                thumb=cover_data,
                                caption=f"🎵 <b>{track_info['artists']}</b> — {track_info['title']}\n💿 {track_info['album']}",
                                parse_mode='HTML'
                            )
                        else:
                            bot.send_audio(
                                call.message.chat.id,
                                audio=audio_data,
                                title=track_info['title'],
                                performer=track_info['main_artist'],
                                duration=track_info.get('duration', 0),
                                caption=f"🎵 <b>{track_info['artists']}</b> — {track_info['title']}",
                                parse_mode='HTML'
                            )
                        
                        bot.answer_callback_query(call.id, "✅ Полный трек отправлен!")
                    except Exception as e:
                        logger.error(f"Ошибка отправки аудио: {e}")
                        bot.send_message(
                            call.message.chat.id,
                            f"❌ Не удалось отправить аудио: {str(e)[:100]}"
                        )
                else:
                    bot.send_message(
                        call.message.chat.id,
                        f"❌ Не удалось найти полную версию трека на YouTube\n\n"
                        f"🎵 {track_info['artists']} — {track_info['title']}\n\n"
                        f"💡 Попробуйте использовать 30-секундное превью или ссылки на платформы"
                    )
                    bot.answer_callback_query(call.id, "❌ Трек не найден на YouTube", show_alert=False)
                    
            except Exception as e:
                logger.error(f"Ошибка отправки полного трека: {e}")
                bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)[:50]}", show_alert=True)
                try:
                    bot.send_message(
                        call.message.chat.id,
                        f"❌ Произошла ошибка при загрузке трека\n\n{str(e)[:200]}"
                    )
                except:
                    pass
            return

        if call.data.startswith('bio_album_'):
            artist_name = call.data.replace('bio_album_', '').replace('_', ' ')
            bot.answer_callback_query(call.id, "🎤 Загружаем биографию...")
            send_artist_bio(call.message, artist_name)
            return

        # === ОБРАБОТЧИК ОТМЕНЫ ПОИСКА ===
        if call.data == 'cancel_search':
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
                bot.answer_callback_query(call.id, "❌ Поиск отменён")
            except Exception as e:
                logger.error(f"Ошибка отмены поиска: {e}")
                bot.answer_callback_query(call.id, "❌ Ошибка")
            return
        
        callback_data = callback_storage.get(call.data, {})
        action = callback_data.get('action', '')
        track_id = callback_data.get('track_id', 0)
        
        if not action:
            parts = call.data.split('_')
            if len(parts) >= 2:
                action = parts[0]
                if parts[1].isdigit():
                    track_id = int(parts[1])
                else:
                    bot.answer_callback_query(call.id, "❌ Неверный ID")
                    return
            else:
                bot.answer_callback_query(call.id, "❌ Неверный формат")
                return
        
        if action == 'play':
            handle_play_preview(call, track_id)
        
        elif action == 'bio':
            if track_id in user_track_cache:
                track_info = user_track_cache[track_id]
                send_artist_bio(call.message, track_info['main_artist'])
                bot.answer_callback_query(call.id, "✅ Биография загружается...")
            else:
                bot.answer_callback_query(call.id, "❌ Трек не найден в кэше")
        
        elif action == 'release':
            handle_release_date(call, track_id)
        
        elif action == 'fav':
            bot.answer_callback_query(
                call.id,
                f"⭐ Трек добавлен в избранное!",
                show_alert=False
            )
        
        elif call.data == 'close_release':
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
                bot.answer_callback_query(call.id, "✅ Сообщение закрыто")
            except Exception as e:
                logger.error(f"Ошибка удаления сообщения: {e}")
                bot.answer_callback_query(call.id, "❌ Не удалось закрыть")
        
        else:
            bot.answer_callback_query(call.id, "❌ Неизвестная команда")
            
    except Exception as e:
        logger.error(f"Ошибка в callback: {e}")
        try:
            bot.answer_callback_query(call.id, f"Ошибка: {str(e)[:50]}")
        except:
            pass

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ CALLBACK ===
def handle_play_preview(call, track_id: int):
    bot.answer_callback_query(call.id, "⏳ Загрузка превью...")
    
    preview_url = get_track_preview(track_id)
    track_info = user_track_cache.get(track_id, {})
    
    if not preview_url:
        bot.answer_callback_query(call.id, "❌ Превью недоступно")
        return
    
    try:
        audio_response = requests.get(preview_url, timeout=30)
        if audio_response.status_code == 200:
            bot.send_voice(
                call.message.chat.id,
                voice=audio_response.content,
                caption=f"🎧 {track_info.get('artists', '')} — {track_info.get('title', 'Трек')} (30 сек)",
                duration=30
            )
            bot.answer_callback_query(call.id, "✅ Превью отправлено!")
        else:
            bot.answer_callback_query(call.id, "❌ Ошибка загрузки")
    except Exception as e:
        logger.error(f"Ошибка отправки превью: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при отправке")

def handle_release_date(call, track_id: int):
    bot.answer_callback_query(call.id, "⏳ Поиск даты релиза...")
    
    release_date = get_track_release_date(track_id)
    track_info = user_track_cache.get(track_id, {})
    
    artist = track_info.get('artists', 'Неизвестный исполнитель')
    title = track_info.get('title', 'Неизвестный трек')
    
    if release_date:
        date_text = (
            f"📆 <b>Дата релиза</b>\n\n"
            f"🎵 <b>{artist}</b> — {title}\n"
            f"📅 <b>Релиз состоялся:</b> {release_date}"
        )
        
        if track_info.get('release_date'):
            relative_time = get_relative_time(track_info['release_date'])
            if relative_time:
                date_text += f"\n⏳ <b>Прошло:</b> {relative_time}"
        
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton(
            "✖ Закрыть",
            callback_data="close_release"
        ))
        keyboard.add(InlineKeyboardButton(
            "🔗 Открыть на Deezer",
            url=f"https://www.deezer.com/track/{track_id}"
        ))
        
        bot.send_message(
            call.message.chat.id,
            date_text,
            parse_mode='HTML',
            reply_markup=keyboard
        )
        bot.answer_callback_query(call.id, "✅ Дата релиза показана")
    else:
        error_text = (
            f"❌ Не удалось найти дату релиза\n\n"
            f"🎵 <b>{artist}</b> — {title}\n\n"
            f"💡 Возможно, дата релиза недоступна"
        )
        
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton(
            "🔗 Открыть на Deezer",
            url=f"https://www.deezer.com/track/{track_id}"
        ))
        keyboard.add(InlineKeyboardButton(
            "✖ Закрыть",
            callback_data="close_release"
        ))
        
        bot.send_message(
            call.message.chat.id,
            error_text,
            parse_mode='HTML',
            reply_markup=keyboard
        )
        bot.answer_callback_query(
            call.id,
            "❌ Дата релиза не найдена",
            show_alert=True
        )

def get_track_release_date(track_id: int) -> Optional[str]:
    try:
        if track_id in user_track_cache:
            track_info = user_track_cache[track_id]
            if track_info.get('formatted_date'):
                return track_info['formatted_date']
            if track_info.get('release_date'):
                return format_release_date(track_info['release_date'])
        
        url = f"https://api.deezer.com/track/{track_id}"
        response = requests.get(url, timeout=15)
        
        if response.status_code != 200:
            return None
        
        track = response.json()
        release_date = None
        
        if track.get('release_date'):
            release_date = track['release_date']
        
        if not release_date and track.get('album'):
            if track['album'].get('release_date'):
                release_date = track['album']['release_date']
            
            if not release_date and track['album'].get('id'):
                album_id = track['album']['id']
                album_url = f"https://api.deezer.com/album/{album_id}"
                album_response = requests.get(album_url, timeout=15)
                if album_response.status_code == 200:
                    album_data = album_response.json()
                    if album_data.get('release_date'):
                        release_date = album_data['release_date']
        
        if release_date:
            formatted = format_release_date(release_date)
            
            if track_id in user_track_cache:
                user_track_cache[track_id]['formatted_date'] = formatted
                user_track_cache[track_id]['release_date'] = release_date
            
            return formatted
        
        return None
        
    except Exception as e:
        logger.error(f"Ошибка получения даты релиза: {e}")
        return None

# === ОБРАБОТЧИК MINI APP ===
@bot.message_handler(content_types=['web_app_data'])
def handle_web_app(message: Message):
    try:
        logger.info(f"📩 Получены данные: {message.web_app_data.data}")
        
        data = json.loads(message.web_app_data.data)
        action = data.get('action')
        
        if action == 'search':
            query = data.get('query', '').strip()
            logger.info(f"🔍 Поиск в Mini App: {query}")
            
            if not query or len(query) < 1:
                bot.send_message(message.chat.id, json.dumps({
                    'type': 'search_result',
                    'track': None,
                    'error': 'Слишком короткий запрос'
                }))
                return
            
            track_info = search_track_with_retry(query)
            
            if track_info:
                ai_fact = generate_ai_fact(track_info['main_artist'], track_info['title'])
                song_meaning = get_song_meaning(track_info['title'], track_info['main_artist'])
                
                result = {
                    'type': 'search_result',
                    'track': {
                        'title': track_info['title'],
                        'artists': track_info['artists'],
                        'album': track_info['album'],
                        'year': track_info.get('year'),
                        'release_date': track_info.get('formatted_date') or track_info.get('release_date'),
                        'relative_time': get_relative_time(track_info.get('release_date')) if track_info.get('release_date') else None,
                        'duration': track_info['duration_str'],
                        'main_artist': track_info['main_artist'],
                        'links': track_info['links'],
                        'preview_url': track_info.get('preview_url'),
                        'cover_url': track_info.get('cover_url'),
                        'ai_fact': ai_fact,
                        'song_meaning': song_meaning['meaning'] if song_meaning else None,
                        'song_emotion': song_meaning['emotion'] if song_meaning else None
                    }
                }
                
                bot.send_message(message.chat.id, json.dumps(result))
                logger.info(f"✅ Трек найден: {track_info['title']}")
                return
            
            album_info = search_album_with_retry(query)
            if album_info:
                result = {
                    'type': 'album_result',
                    'album': {
                        'title': album_info['title'],
                        'artist': album_info['artist'],
                        'year': album_info.get('year'),
                        'release_date': format_release_date(album_info.get('release_date')),
                        'relative_time': get_relative_time(album_info.get('release_date')) if album_info.get('release_date') else None,
                        'track_count': album_info.get('track_count', 0),
                        'cover_url': album_info.get('cover_url'),
                        'link': album_info['link'],
                        'tracks': [{'title': t['title']} for t in album_info.get('tracks', [])[:5]]
                    }
                }
                bot.send_message(message.chat.id, json.dumps(result))
                logger.info(f"💿 Альбом найден: {album_info['title']}")
            else:
                bot.send_message(message.chat.id, json.dumps({
                    'type': 'search_result',
                    'track': None,
                    'error': f'Ничего не найдено по запросу "{query}"'
                }))
                logger.warning(f"❌ Ничего не найдено: {query}")
        
        elif action == 'subscribe_artist':
            artist_name = data.get('artist', '').strip()
            user_id = str(message.from_user.id)
            
            if not artist_name:
                bot.send_message(message.chat.id, json.dumps({
                    'type': 'subscribe_result',
                    'success': False,
                    'message': 'Укажите имя исполнителя'
                }))
                return
            
            if user_id not in user_subscriptions:
                user_subscriptions[user_id] = []
            
            if any(a['name'].lower() == artist_name.lower() for a in user_subscriptions[user_id]):
                bot.send_message(message.chat.id, json.dumps({
                    'type': 'subscribe_result',
                    'success': False,
                    'message': f'Вы уже подписаны на {artist_name}'
                }))
            else:
                user_subscriptions[user_id].append({'name': artist_name})
                with open(SUBSCRIPTIONS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(user_subscriptions, f, ensure_ascii=False, indent=2)
                
                bot.send_message(message.chat.id, json.dumps({
                    'type': 'subscribe_result',
                    'success': True,
                    'message': f'Подписка на {artist_name} оформлена!'
                }))
        
        else:
            logger.warning(f"⚠️ Неизвестное действие: {action}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка в web_app: {e}")
        try:
            bot.send_message(message.chat.id, json.dumps({
                'type': 'error',
                'message': str(e)
            }))
        except:
            pass

# ============================================================
# === ФУНКЦИЯ ДЛЯ ОТСЛЕЖИВАНИЯ НОВЫХ РЕЛИЗОВ ===
# ============================================================

def get_artist_new_release(artist_name: str) -> Optional[Dict[str, Any]]:
    try:
        encoded_name = urllib.parse.quote(artist_name)
        url = f"https://music.yandex.ru/artist/{encoded_name}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        result = {
            'has_new_release': False,
            'release_title': None,
            'release_date': None,
            'release_type': None,
            'cover_url': None,
            'link': None
        }
        
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    if data.get('@type') == 'MusicGroup' and data.get('album'):
                        albums = data.get('album', [])
                        if albums:
                            latest = albums[0] if isinstance(albums, list) else albums
                            if isinstance(latest, dict):
                                result['release_title'] = latest.get('name')
                                result['release_date'] = latest.get('datePublished')
                                result['cover_url'] = latest.get('image')
                                result['link'] = latest.get('url')
                                result['has_new_release'] = True
                                break
            except:
                pass
        
        if not result['has_new_release']:
            release_blocks = soup.find_all(['div', 'a'], class_=re.compile(r'album|release|track', re.I))
            for block in release_blocks[:3]:
                title_elem = block.find(class_=re.compile(r'title|name', re.I))
                img_elem = block.find('img')
                
                if title_elem:
                    result['release_title'] = title_elem.text.strip()
                    result['has_new_release'] = True
                    
                    if img_elem:
                        img_url = img_elem.get('src') or img_elem.get('data-src')
                        if img_url:
                            if img_url.startswith('//'):
                                img_url = 'https:' + img_url
                            result['cover_url'] = img_url
                    
                    link_elem = block.find('a', href=re.compile(r'/album/|/track/', re.I))
                    if link_elem:
                        href = link_elem.get('href')
                        if href:
                            result['link'] = 'https://music.yandex.ru' + href if href.startswith('/') else href
                    break
        
        if result['has_new_release'] and result['release_title']:
            title_lower = result['release_title'].lower()
            if 'single' in title_lower or 'сингл' in title_lower:
                result['release_type'] = 'single'
            elif 'ep' in title_lower or 'мини-альбом' in title_lower:
                result['release_type'] = 'ep'
            else:
                result['release_type'] = 'album'
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка проверки новых релизов для {artist_name}: {e}")
        return None

def get_upcoming_release(artist_name: str) -> Optional[Dict[str, Any]]:
    """Проверяет, есть ли у исполнителя предстоящий релиз (сначала Яндекс Музыка)"""
    try:
        # ===== 1. СНАЧАЛА ПРОВЕРЯЕМ ЯНДЕКС МУЗЫКУ =====
        encoded_name = urllib.parse.quote(artist_name)
        url = f"https://music.yandex.ru/artist/{encoded_name}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Ищем будущие релизы
            upcoming = soup.find_all(['div', 'a'], class_=re.compile(r'upcoming|future|release|soon|preorder', re.I))
            
            for item in upcoming:
                text = item.get_text(' ', strip=True)
                
                # Ищем дату
                date_match = re.search(r'(\d{1,2}\s+[а-я]+\s+\d{4}|\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2})', text, re.IGNORECASE)
                
                if date_match:
                    date_str = date_match.group(1)
                    try:
                        for fmt in ['%d %B %Y', '%d %b %Y', '%d.%m.%Y', '%Y-%m-%d', '%d %B %Y года']:
                            try:
                                # Очищаем строку от лишнего
                                clean_date = re.sub(r'года|year', '', date_str).strip()
                                release_dt = datetime.strptime(clean_date, fmt)
                                now = datetime.now()
                                days_diff = (release_dt - now).days
                                
                                # Если релиз в будущем (через 0-30 дней)
                                if 0 <= days_diff <= 30:
                                    title_elem = item.find(class_=re.compile(r'title|name', re.I))
                                    title = title_elem.text.strip() if title_elem else 'Новый релиз'
                                    
                                    # Ищем обложку
                                    img_elem = item.find('img')
                                    cover_url = None
                                    if img_elem:
                                        cover_url = img_elem.get('src') or img_elem.get('data-src')
                                    
                                    # Ищем ссылку
                                    link_elem = item.find('a', href=re.compile(r'/album/|/track/', re.I))
                                    link = None
                                    if link_elem:
                                        href = link_elem.get('href', '')
                                        if href:
                                            link = 'https://music.yandex.ru' + href if href.startswith('/') else href
                                    
                                    return {
                                        'has_upcoming': True,
                                        'release_title': title,
                                        'release_date': date_str,
                                        'release_type': 'album',
                                        'artist': artist_name,
                                        'days_left': days_diff,
                                        'cover_url': cover_url,
                                        'link': link,
                                        'source': 'yandex'
                                    }
                            except:
                                continue
                    except:
                        pass
        
        # ===== 2. ЕСЛИ В ЯНДЕКС НЕ НАШЛИ — ПРОВЕРЯЕМ DEEZER =====
        search_url = f"https://api.deezer.com/search/artist?q={urllib.parse.quote(artist_name)}&limit=1"
        response = requests.get(search_url, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('data') and len(data['data']) > 0:
                artist_id = data['data'][0]['id']
                
                albums_url = f"https://api.deezer.com/artist/{artist_id}/albums?limit=10"
                albums_response = requests.get(albums_url, timeout=15)
                
                if albums_response.status_code == 200:
                    albums_data = albums_response.json()
                    if albums_data.get('data'):
                        for album in albums_data['data']:
                            release_date = album.get('release_date', '')
                            if release_date:
                                try:
                                    release_dt = datetime.strptime(release_date, '%Y-%m-%d')
                                    now = datetime.now()
                                    days_diff = (release_dt - now).days
                                    
                                    if 0 <= days_diff <= 30:
                                        return {
                                            'has_upcoming': True,
                                            'release_title': album.get('title', 'Новый альбом'),
                                            'release_date': release_date,
                                            'release_type': 'album',
                                            'cover_url': album.get('cover_xl') or album.get('cover_big'),
                                            'link': album.get('link', ''),
                                            'artist': artist_name,
                                            'days_left': days_diff,
                                            'source': 'deezer'
                                        }
                                except:
                                    pass
        
        return None
        
    except Exception as e:
        logger.error(f"Ошибка проверки предстоящих релизов для {artist_name}: {e}")
        return None

def check_new_releases_for_subscriptions():
    if not user_subscriptions:
        return []
    
    new_releases = []
    release_check_file = 'last_release_check.json'
    
    last_check = {}
    if os.path.exists(release_check_file):
        try:
            with open(release_check_file, 'r', encoding='utf-8') as f:
                last_check = json.load(f)
        except:
            pass
    
    current_time = time.time()
    check_interval = 3600 * 6
    
    for user_id, artists in user_subscriptions.items():
        for artist in artists:
            artist_name = artist.get('name', '')
            if not artist_name:
                continue
            
            last_check_time = last_check.get(artist_name, 0)
            if current_time - last_check_time < check_interval:
                continue
            
            release = get_artist_new_release(artist_name)
            if release and release.get('has_new_release'):
                release['artist'] = artist_name
                release['user_id'] = user_id
                new_releases.append(release)
            
            last_check[artist_name] = current_time
    
    try:
        with open(release_check_file, 'w', encoding='utf-8') as f:
            json.dump(last_check, f, ensure_ascii=False, indent=2)
    except:
        pass
    
    return new_releases

def send_new_release_notification(chat_id: int, release: Dict[str, Any]):
    artist = release.get('artist', 'Неизвестный исполнитель')
    title = release.get('release_title', 'Новый релиз')
    release_type = release.get('release_type', 'album')
    
    type_emoji = {'album': '💿', 'single': '🎵', 'ep': '📀'}
    type_name = {'album': 'Альбом', 'single': 'Сингл', 'ep': 'EP'}
    
    emoji = type_emoji.get(release_type, '💿')
    type_label = type_name.get(release_type, 'Релиз')
    
    text = (
        f"🎉 <b>НОВЫЙ РЕЛИЗ!</b>\n\n"
        f"{emoji} <b>{artist}</b>\n"
        f"📀 <b>{type_label}:</b> {title}\n"
    )
    
    if release.get('release_date'):
        text += f"📅 <b>Дата выхода:</b> {release['release_date']}\n"
    
    text += f"\n🔔 <b>Вы подписаны на {artist}!</b>"
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    if release.get('link'):
        keyboard.add(InlineKeyboardButton(
            f"🎧 Слушать на Яндекс Музыке",
            url=release['link']
        ))
    
    keyboard.add(
        InlineKeyboardButton(
            f"🎤 Биография {artist}",
            callback_data=f"bio_from_release_{urllib.parse.quote(artist)}"
        ),
        InlineKeyboardButton(
            f"🔍 Все релизы",
            url=f"https://music.yandex.ru/search?text={urllib.parse.quote(artist)}"
        )
    )
    
    cover_url = release.get('cover_url')
    if cover_url:
        try:
            cover_response = requests.get(cover_url, timeout=10)
            if cover_response.status_code == 200:
                bot.send_photo(chat_id, photo=cover_response.content, caption=text, parse_mode='HTML', reply_markup=keyboard)
                return
        except:
            pass
    
    bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=keyboard, disable_web_page_preview=True)

def check_and_notify_new_releases():
    try:
        new_releases = check_new_releases_for_subscriptions()
        for release in new_releases:
            user_id = release.get('user_id')
            if user_id:
                try:
                    send_new_release_notification(user_id, release)
                    time.sleep(0.5)
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления для {user_id}: {e}")
        
        if new_releases:
            logger.info(f"✅ Отправлено {len(new_releases)} уведомлений о новых релизах")
        
        return len(new_releases)
        
    except Exception as e:
        logger.error(f"Ошибка проверки новых релизов: {e}")
        return 0

@bot.message_handler(commands=['checkreleases'])
def check_releases_command(message: Message):
    """Проверяет предстоящие релизы у исполнителя"""
    query = message.text.replace('/checkreleases', '', 1).strip()
    
    # Если есть аргумент — проверяем конкретного исполнителя
    if query:
        try:
            bot.send_chat_action(message.chat.id, 'typing')
            status_msg = bot.reply_to(message, f"🔍 Проверяем релизы для {query}...")
            
            release = get_upcoming_release(query)
            bot.delete_message(message.chat.id, status_msg.message_id)
            
            if release and release.get('has_upcoming'):
                days = release.get('days_left', 0)
                
                if days == 0:
                    date_text = "СЕГОДНЯ! 🎉"
                elif days == 1:
                    date_text = "ЗАВТРА! 🔥"
                else:
                    date_text = f"через {days} дней"
                
                text = (
                    f"🎉 <b>НОВЫЙ РЕЛИЗ У {query.upper()}!</b>\n\n"
                    f"💿 <b>{release.get('release_title', 'Новый альбом')}</b>\n"
                    f"📅 <b>Выходит:</b> {date_text}\n"
                )
                
                if release.get('release_date'):
                    formatted = format_release_date(release['release_date'])
                    if formatted:
                        text += f"📆 <b>Дата:</b> {formatted}\n"
                
                keyboard = InlineKeyboardMarkup(row_width=2)
                
                if release.get('link'):
                    keyboard.add(InlineKeyboardButton(
                        "🎧 Предзаказ на Deezer",
                        url=release['link']
                    ))
                
                keyboard.add(
                    InlineKeyboardButton(
                        "🎤 Биография",
                        callback_data=f"bio_from_release_{urllib.parse.quote(query)}"
                    ),
                    InlineKeyboardButton(
                        "🔍 Поискать треки",
                        callback_data=f"search_artist_{urllib.parse.quote(query)}"
                    )
                )
                
                if release.get('cover_url'):
                    try:
                        cover_response = requests.get(release['cover_url'], timeout=10)
                        if cover_response.status_code == 200:
                            bot.send_photo(
                                message.chat.id,
                                photo=cover_response.content,
                                caption=text,
                                parse_mode='HTML',
                                reply_markup=keyboard
                            )
                            return
                    except:
                        pass
                
                bot.send_message(
                    message.chat.id,
                    text,
                    parse_mode='HTML',
                    reply_markup=keyboard
                )
            else:
                bot.reply_to(
                    message,
                    f"❌ У {query} нет анонсированных релизов в ближайшее время.\n\n"
                    f"💡 Проверьте позже или подпишитесь на уведомления:\n"
                    f"/subscribe {query}",
                    parse_mode='HTML'
                )
            return
            
        except Exception as e:
            logger.error(f"Ошибка в check_releases_command: {e}")
            bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")
            return
    
    # Если нет аргумента — проверяем все подписки пользователя
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        status_msg = bot.reply_to(message, "🔍 Проверяем релизы для ваших подписок...")
        
        user_id = str(message.from_user.id)
        
        if user_id not in user_subscriptions or not user_subscriptions[user_id]:
            bot.delete_message(message.chat.id, status_msg.message_id)
            bot.reply_to(
                message,
                "📭 У вас нет подписок!\n\n"
                "💡 Используйте /subscribe <имя>, чтобы подписаться на исполнителя\n"
                "📌 Пример: /subscribe Асия\n\n"
                "📌 Или проверьте конкретного исполнителя:\n"
                "/checkreleases Асия",
                parse_mode='HTML'
            )
            return
        
        found_releases = []
        
        for artist in user_subscriptions[user_id]:
            artist_name = artist.get('name', '')
            if artist_name:
                release = get_upcoming_release(artist_name)
                if release and release.get('has_upcoming'):
                    release['artist'] = artist_name
                    found_releases.append(release)
                time.sleep(0.3)
        
        bot.delete_message(message.chat.id, status_msg.message_id)
        
        if found_releases:
            text = "🎉 <b>ПРЕДСТОЯЩИЕ РЕЛИЗЫ</b>\n\n"
            
            for release in found_releases:
                days = release.get('days_left', 0)
                
                if days == 0:
                    date_text = "🔥 СЕГОДНЯ!"
                elif days == 1:
                    date_text = "🔥 ЗАВТРА!"
                else:
                    date_text = f"через {days} дн."
                
                text += (
                    f"🎤 <b>{release['artist']}</b>\n"
                    f"💿 {release.get('release_title', 'Новый релиз')}\n"
                    f"📅 {date_text}\n\n"
                )
            
            bot.send_message(
                message.chat.id,
                text,
                parse_mode='HTML'
            )
        else:
            artists_list = '\n'.join([f"🎤 {a['name']}" for a in user_subscriptions[user_id]])
            bot.reply_to(
                message,
                f"🔔 Нет анонсированных релизов для ваших подписок.\n\n"
                f"📋 <b>Ваши подписки:</b>\n{artists_list}\n\n"
                f"💡 Проверьте конкретного исполнителя:\n"
                f"/checkreleases Асия",
                parse_mode='HTML'
            )
            
    except Exception as e:
        logger.error(f"Ошибка в check_releases_command: {e}")
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")

# === ФУНКЦИЯ ДЛЯ ПОВТОРНОГО ПОДКЛЮЧЕНИЯ ===
def run_bot_with_retry():
    # ===== УДАЛЯЕМ WEBHOOK ПЕРЕД ЗАПУСКОМ =====
    try:
        bot.remove_webhook()
        logger.info("✅ Webhook удалён")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось удалить webhook: {e}")
    
    retry_count = 0
    max_retries = 10
    
    while retry_count < max_retries:
        try:
            logger.info("🚀 Запуск бота...")
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except KeyboardInterrupt:
            logger.info("👋 Бот остановлен пользователем")
            break
        except Exception as e:
            retry_count += 1
            logger.error(f"❌ Ошибка: {e}")
            logger.info(f"🔄 Переподключение через {RETRY_DELAY} секунд... (попытка {retry_count}/{max_retries})")
            time.sleep(RETRY_DELAY)
    
    if retry_count >= max_retries:
        logger.error("❌ Превышено максимальное количество попыток подключения")

# === ФУНКЦИЯ ДЛЯ ФОНОВОЙ ПРОВЕРКИ НОВЫХ РЕЛИЗОВ ===
def start_release_checker():
    def check_loop():
        while True:
            try:
                time.sleep(3600 * 6)  # 6 часов
                check_and_notify_new_releases()
            except Exception as e:
                logger.error(f"Ошибка в фоновой проверке: {e}")
    
    thread = threading.Thread(target=check_loop, daemon=True)
    thread.start()
    logger.info("✅ Запущен фоновый проверщик новых релизов")

# === ЗАПУСК ===
if __name__ == '__main__':
    print("=" * 60)
    print("🎵 LE MONDE MUSIC BOT v42.0")
    print("🎧 30-секундное превью для КАЖДОГО трека")
    print("🎵 ПОЛНОЕ ПРОСЛУШИВАНИЕ ТРЕКОВ (из YouTube)")
    print("📆 С датой релиза и ОТНОСИТЕЛЬНЫМ ВРЕМЕНЕМ")
    print("📖 Со смыслом песен")
    print("🎤 Биография из Deezer")
    print("💿 Все альбомы с ▶️ для каждого трека")
    print("🎵 Все треки с ▶️ для прослушивания")
    print("🖼 АВТОМАТИЧЕСКАЯ ГЕНЕРАЦИЯ ОБЛОЖЕК, если нет в Deezer")
    print("🔍 ИЩЕТ В 4-Х ИСТОЧНИКАХ:")
    print("   • Deezer")
    print("   • Яндекс Музыка")
    print("   • YouTube Music")
    print("   • YouTube")
    print("🔢 ПОДДЕРЖИВАЕТ ПОИСК ПО ЧИСЛАМ (911, 21, 7 rings и т.д.)")
    print("🔍 НАХОДИТ ВСЕ ТРЕКИ И АЛЬБОМЫ!")
    print("🎫 КРАСИВЫЙ вывод концертов через Яндекс Музыку")
    print("🔔 НОВЫЕ РЕЛИЗЫ подписанных исполнителей")
    print("🔄 С автоматическим переподключением")
    print("=" * 60)
    
    try:
        import bs4
        print("✅ BeautifulSoup установлен")
    except ImportError:
        print("⚠️ BeautifulSoup не установлен! Установите: pip install beautifulsoup4")
    
    try:
        import yt_dlp
        print("✅ yt-dlp установлен (доступны полные треки)")
    except ImportError:
        print("⚠️ yt-dlp НЕ установлен! Установите: pip install yt-dlp")
        print("   Функция 'Полный трек' будет недоступна")
    
    if PIL_AVAILABLE:
        print("✅ Pillow установлен (доступна генерация обложек)")
    else:
        print("⚠️ Pillow НЕ установлен! Установите: pip install Pillow")
        print("   Обложки будут браться только из Deezer или Google Images")
    
    try:
        if os.path.exists(SUBSCRIPTIONS_FILE):
            with open(SUBSCRIPTIONS_FILE, 'r', encoding='utf-8') as f:
                user_subscriptions = json.load(f)
                logger.info(f"✅ Загружено {len(user_subscriptions)} подписок")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка загрузки подписок: {e}")
    
    set_bot_commands()
    start_release_checker()
    run_bot_with_retry()
