from mcp.server.fastmcp import FastMCP

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
import requests
import re
from dotenv import load_dotenv
import os
load_dotenv()

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_API_URL = 'https://www.googleapis.com/youtube/v3'

# Create an MCP server
mcp = FastMCP("youtube_agent_server")

### Tool 1 : 유튜브 영상 URL에 대한 자막을 가져옵니다 (개선된 버전)

@mcp.tool()
def get_youtube_transcript(url: str) -> str:
    """ 유튜브 영상 URL에 대한 자막을 가져옵니다."""
    
    def extract_video_id(url: str) -> str:
        """YouTube URL에서 비디오 ID 추출"""
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com\/watch\?.*v=([a-zA-Z0-9_-]{11})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        raise ValueError("유효하지 않은 YouTube URL입니다")

    def method1_youtube_transcript_api(video_id: str) -> tuple:
        """방법 1: youtube-transcript-api 사용 (최대한 간단한 버전)"""
        try:
            # 모든 가능한 언어로 시도
            all_languages = ['ko', 'en', 'en-US', 'en-GB', 'ja', 'zh', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'ar', 'hi', 'th', 'vi', 'id', 'tr', 'pl', 'nl', 'sv', 'da', 'no', 'fi', 'cs', 'hu', 'ro', 'bg', 'hr', 'sk', 'sl', 'et', 'lv', 'lt', 'el', 'he', 'fa', 'ur', 'bn', 'ta', 'te', 'ml', 'kn', 'gu', 'pa', 'or', 'as', 'ne', 'si', 'my', 'km', 'lo', 'ka', 'am', 'sw', 'zu', 'af', 'sq', 'eu', 'be', 'bs', 'ca', 'cy', 'eo', 'gl', 'is', 'mk', 'mt', 'ms', 'tl', 'uk', 'uz', 'vi', 'yi']
            
            # 먼저 자막 목록 확인
            try:
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                
                # 사용 가능한 자막들 확인
                available_transcripts = []
                for transcript in transcript_list:
                    available_transcripts.append(transcript.language_code)
                
                print(f"사용 가능한 자막 언어: {available_transcripts}")
                
                # 사용 가능한 자막 중에서 우선순위 언어 시도
                preferred_languages = ['ko', 'en', 'en-US', 'en-GB']
                for lang in preferred_languages:
                    if lang in available_transcripts:
                        try:
                            transcript = transcript_list.find_transcript([lang])
                            transcript_data = transcript.fetch()
                            text = " ".join([entry["text"] for entry in transcript_data])
                            if text.strip():
                                return text, f"성공 (언어: {lang})"
                        except Exception as e:
                            continue
                
                # 첫 번째 사용 가능한 자막 시도
                try:
                    first_transcript = next(iter(transcript_list))
                    transcript_data = first_transcript.fetch()
                    text = " ".join([entry["text"] for entry in transcript_data])
                    if text.strip():
                        return text, f"성공 (언어: {first_transcript.language_code})"
                except Exception as e:
                    pass
                    
            except Exception as e:
                print(f"자막 목록 조회 실패: {e}")
                
            # 직접 언어별 시도
            for lang in ['ko', 'en']:
                try:
                    transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang])
                    text = " ".join([entry["text"] for entry in transcript])
                    if text.strip():
                        return text, f"성공 (직접 - {lang})"
                except Exception as e:
                    continue
                
        except Exception as e:
            print(f"youtube-transcript-api 오류: {e}")
        
        return None, "실패"

    def method2_direct_api_call(video_id: str) -> tuple:
        """방법 2: 직접 YouTube API 호출"""
        try:
            # YouTube의 자막 API 직접 호출
            for lang in ['ko', 'en']:
                captions_url = f"https://www.youtube.com/api/timedtext?v={video_id}&lang={lang}&fmt=srv3"
                response = requests.get(captions_url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }, timeout=10)
                
                if response.status_code == 200 and response.text.strip():
                    try:
                        root = ET.fromstring(response.text)
                        texts = []
                        for text_elem in root.findall('.//text'):
                            if text_elem.text:
                                # HTML 엔티티 디코딩
                                clean_text = text_elem.text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
                                texts.append(clean_text)
                        
                        if texts:
                            return " ".join(texts), f"성공 (직접 API - {lang})"
                    except ET.ParseError:
                        continue
                        
        except Exception as e:
            pass
        
        return None, "실패"
    
    def method3_yt_dlp_extraction(video_id: str) -> tuple:
        """방법 3: yt-dlp를 사용한 자막 추출"""
        try:
            import subprocess
            import json
            
            # yt-dlp로 자막 정보 가져오기
            cmd = [
                'yt-dlp',
                '--list-subs',
                '--no-download',
                f'https://www.youtube.com/watch?v={video_id}'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and 'ko' in result.stdout:
                # 한국어 자막이 있으면 다운로드
                download_cmd = [
                    'yt-dlp',
                    '--write-subs',
                    '--write-auto-subs',
                    '--sub-langs', 'ko,en',
                    '--skip-download',
                    '--output', f'{video_id}.%(ext)s',
                    f'https://www.youtube.com/watch?v={video_id}'
                ]
                
                download_result = subprocess.run(download_cmd, capture_output=True, text=True, timeout=60)
                
                if download_result.returncode == 0:
                    # 다운로드된 자막 파일 찾기
                    import glob
                    srt_files = glob.glob(f'{video_id}*.srt')
                    if srt_files:
                        with open(srt_files[0], 'r', encoding='utf-8') as f:
                            content = f.read()
                        # SRT 파일 정리
                        lines = content.split('\n')
                        text_lines = []
                        for line in lines:
                            if line and not line.isdigit() and '-->' not in line:
                                text_lines.append(line.strip())
                        if text_lines:
                            return ' '.join(text_lines), "성공 (yt-dlp)"
                            
        except Exception as e:
            pass
        
        return None, "실패"
    
    def method4_web_scraping(video_id: str) -> tuple:
        """방법 4: 웹 스크래핑을 통한 자막 추출 (개선된 버전)"""
        try:
            import re
            import urllib.parse
            
            # YouTube 페이지에서 자막 정보 추출
            page_url = f"https://www.youtube.com/watch?v={video_id}"
            response = requests.get(page_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }, timeout=15)
            
            if response.status_code == 200:
                # 다양한 자막 URL 패턴 시도
                patterns = [
                    r'"captions":\{"playerCaptionsTracklistRenderer":\{"captionTracks":\[(.*?)\]',
                    r'"captionTracks":\[(.*?)\]',
                    r'"captions":\{"playerCaptionsTracklistRenderer":\{"captionTracks":\[(.*?)\]\}',
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, response.text)
                    if match:
                        captions_data = match.group(1)
                        
                        # URL 추출 패턴들
                        url_patterns = [
                            r'"baseUrl":"([^"]+)"',
                            r'"url":"([^"]+)"',
                            r'"baseUrl":"([^"]*timedtext[^"]*)"'
                        ]
                        
                        for url_pattern in url_patterns:
                            urls = re.findall(url_pattern, captions_data)
                            
                            for url in urls:
                                try:
                                    # URL 디코딩
                                    decoded_url = urllib.parse.unquote(url)
                                    
                                    # 자막 다운로드
                                    caption_response = requests.get(decoded_url, headers={
                                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                                    }, timeout=10)
                                    
                                    if caption_response.status_code == 200 and caption_response.text.strip():
                                        try:
                                            root = ET.fromstring(caption_response.text)
                                            texts = []
                                            for text_elem in root.findall('.//text'):
                                                if text_elem.text:
                                                    clean_text = text_elem.text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'")
                                                    texts.append(clean_text)
                                            
                                            if texts and len(' '.join(texts).strip()) > 10:  # 최소 길이 체크
                                                return " ".join(texts), "성공 (웹 스크래핑)"
                                        except ET.ParseError:
                                            continue
                                        except Exception:
                                            continue
                                except Exception:
                                    continue
                        
        except Exception as e:
            pass
        
        return None, "실패"
    
    # 메인 로직
    try:
        video_id = extract_video_id(url)
        
        # 여러 방법 시도 (간단한 방법부터)
        methods = [
            method1_youtube_transcript_api,
            method4_web_scraping,
            method2_direct_api_call,
            method3_yt_dlp_extraction
        ]
        
        for method in methods:
            try:
                transcript, status = method(video_id)
                if transcript and len(transcript.strip()) > 0:
                    return transcript
            except Exception as e:
                continue
        
        # 모든 방법 실패 - 오류 대신 빈 결과 반환
        return {
            "content": [],
            "isError": True,
            "errorMessage": f"비디오 ID '{video_id}'의 자막을 가져올 수 없습니다. 자막이 없거나 접근이 제한되어 있을 수 있습니다."
        }
        
    except Exception as e:
        # 예외 발생 시에도 오류 정보 반환
        return {
            "content": [],
            "isError": True,
            "errorMessage": f"자막 추출 중 오류 발생: {str(e)}"
        }

### Tool 2 : 유튜브에서 특정 키워드로 동영상을 검색하고 세부 정보를 가져옵니다
@mcp.tool()
def search_youtube_videos(query: str) -> list:
    """유튜브에서 특정 키워드로 동영상을 검색하고 세부 정보를 가져옵니다"""
    try:
        if not YOUTUBE_API_KEY:
            raise ValueError("YouTube API 키가 설정되지 않았습니다.")
            
        # 1. 동영상 검색
        max_results: int = 20
        search_url = f"{YOUTUBE_API_URL}/search?part=snippet&q={requests.utils.quote(query)}&type=video&maxResults={max_results}&key={YOUTUBE_API_KEY}"

        search_response = requests.get(search_url, timeout=10)
        search_response.raise_for_status()
        search_data = search_response.json()
        
        video_ids = [item['id']['videoId'] for item in search_data.get('items', [])]

        if not video_ids:
            return []

        video_details_url = f"{YOUTUBE_API_URL}/videos?part=snippet,statistics&id={','.join(video_ids)}&key={YOUTUBE_API_KEY}"
        details_response = requests.get(video_details_url, timeout=10)
        details_response.raise_for_status()
        details_data = details_response.json()

        videos = []
        for item in details_data.get('items', []):
            snippet = item.get('snippet', {})
            statistics = item.get('statistics', {})
            thumbnails = snippet.get('thumbnails', {})
            high_thumbnail = thumbnails.get('high', {}) 
            view_count = statistics.get('viewCount')
            like_count = statistics.get('likeCount')

            video_card = {
                "title": snippet.get('title', 'N/A'),
                "publishedDate": snippet.get('publishedAt', ''),
                "channelName": snippet.get('channelTitle', 'N/A'),
                "channelId": snippet.get('channelId', ''),
                "thumbnailUrl": high_thumbnail.get('url', ''),
                "viewCount": int(view_count) if view_count is not None and view_count.isdigit() else 0,
                "likeCount": int(like_count) if like_count is not None and like_count.isdigit() else 0,
                "url": f"https://www.youtube.com/watch?v={item.get('id', '')}",
            }
            videos.append(video_card)

        return videos

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"YouTube API 요청 오류: {str(e)}")
    except Exception as e:
        raise RuntimeError(f"검색 중 오류 발생: {str(e)}")

### Tool 3 : YouTube 동영상 URL로부터 채널 정보와 최근 5개의 동영상을 가져옵니다
@mcp.tool()
def get_channel_info(video_url: str) -> dict:
    """YouTube 동영상 URL로부터 채널 정보와 최근 5개의 동영상을 가져옵니다"""
    
    def extract_video_id(url):
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com\/watch\?.*v=([a-zA-Z0-9_-]{11})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def fetch_recent_videos(channel_id):
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        try:
            response = requests.get(rss_url, timeout=10)
            if response.status_code != 200:
                return []

            root = ET.fromstring(response.text)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            videos = []

            for entry in root.findall('.//atom:entry', ns)[:5]:  
                title_elem = entry.find('./atom:title', ns)
                link_elem = entry.find('./atom:link', ns)
                published_elem = entry.find('./atom:published', ns)
                
                if title_elem is not None and link_elem is not None and published_elem is not None:
                    videos.append({
                        'title': title_elem.text or '',
                        'link': link_elem.attrib.get('href', ''),
                        'published': published_elem.text or '',
                        'updatedDate': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })

            return videos
        except Exception as e:
            print(f"RSS 피드 오류: {str(e)}")
            return []

    try:
        if not YOUTUBE_API_KEY:
            raise ValueError("YouTube API 키가 설정되지 않았습니다.")
            
        video_id = extract_video_id(video_url)
        if not video_id:
            raise ValueError("유효하지 않은 YouTube URL입니다.")

        video_api = f"{YOUTUBE_API_URL}/videos?part=snippet,statistics&id={video_id}&key={YOUTUBE_API_KEY}"
        video_response = requests.get(video_api, timeout=10)
        video_response.raise_for_status()
        video_data = video_response.json()
        
        if not video_data.get('items'):
            raise ValueError("비디오를 찾을 수 없습니다.")

        video_info = video_data['items'][0]
        channel_id = video_info['snippet']['channelId']

        channel_api = f"{YOUTUBE_API_URL}/channels?part=snippet,statistics&id={channel_id}&key={YOUTUBE_API_KEY}"
        channel_response = requests.get(channel_api, timeout=10)
        channel_response.raise_for_status()
        channel_data = channel_response.json()
        
        if not channel_data.get('items'):
            raise ValueError("채널을 찾을 수 없습니다.")

        channel_info = channel_data['items'][0]

        return {
            'channelTitle': channel_info['snippet'].get('title', 'N/A'),
            'channelUrl': f"https://www.youtube.com/channel/{channel_id}",
            'subscriberCount': channel_info['statistics'].get('subscriberCount', '0'),
            'viewCount': channel_info['statistics'].get('viewCount', '0'),
            'videoCount': channel_info['statistics'].get('videoCount', '0'),
            'videos': fetch_recent_videos(channel_id)
        }
    
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"YouTube API 요청 오류: {str(e)}")
    except Exception as e:
        raise RuntimeError(f"채널 정보 조회 중 오류 발생: {str(e)}")

if __name__ == "__main__":
    print("Starting MCP server...")
    mcp.run(transport="stdio")