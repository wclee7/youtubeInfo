import sys
import asyncio
import streamlit as st
import json
from openai import OpenAI
from dotenv import load_dotenv
import subprocess
import time

load_dotenv()

# Windows 호환성
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

class SimpleMCPClient:
    def __init__(self, command, args):
        self.command = command
        self.args = args
        self.process = None
        self.tools = []
        
    async def connect(self):
        """MCP 서버에 연결"""
        try:
            # MCP 서버 프로세스 시작
            self.process = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0,
                encoding='utf-8',
                errors='ignore'
            )
            
            # 잠시 대기
            await asyncio.sleep(1)
            
            # 1. 초기화 메시지 전송
            init_message = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "clientInfo": {
                        "name": "streamlit-client",
                        "version": "1.0.0"
                    }
                }
            }
            
            await self._send_message(init_message)
            init_response = await self._read_message()
            
            if not init_response.get("result"):
                return False
            
            # 2. 초기화 완료 알림
            initialized_message = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            await self._send_message(initialized_message)
            
            # 3. 도구 목록 요청
            tools_message = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list"
            }
            await self._send_message(tools_message)
            tools_response = await self._read_message()
            
            if tools_response.get("result") and "tools" in tools_response["result"]:
                self.tools = tools_response["result"]["tools"]
                return True
            
            return False
            
        except Exception as e:
            st.error(f"MCP 서버 연결 오류: {str(e)}")
            return False
    
    async def _send_message(self, message):
        """메시지 전송"""
        if self.process and self.process.stdin:
            message_str = json.dumps(message) + "\n"
            self.process.stdin.write(message_str)
            self.process.stdin.flush()
    
    async def _read_message(self):
        """메시지 수신"""
        if self.process and self.process.stdout:
            line = self.process.stdout.readline()
            if line:
                return json.loads(line.strip())
        return {}
    
    async def call_tool(self, tool_name, arguments):
        """도구 호출"""
        try:
            call_message = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            
            await self._send_message(call_message)
            response = await self._read_message()
            
            if response.get("result"):
                return response["result"]
            else:
                return None
                
        except Exception as e:
            st.error(f"도구 호출 오류: {str(e)}")
            return None
    
    def disconnect(self):
        """연결 종료"""
        if self.process:
            self.process.terminate()
            self.process.wait()

# MCP 서버 설정
@st.cache_resource
async def setup_mcp_servers():
    try:
        mcp_client = SimpleMCPClient("python", ["mcp_server.py"])
        if await mcp_client.connect():
            return mcp_client
        else:
            st.error("MCP 서버 연결 실패")
            return None
    except Exception as e:
        st.error(f"MCP 서버 설정 오류: {str(e)}")
        return None

# 간단한 AI 응답 생성 함수
async def generate_response(user_message, mcp_client):
    """사용자 메시지에 대한 AI 응답 생성"""
    try:
        # 간단한 키워드 기반 응답 로직
        if "검색" in user_message or "찾아" in user_message or "영상" in user_message:
            # 검색어 추출 (간단한 방법)
            search_query = user_message.replace("검색", "").replace("찾아", "").replace("영상", "").strip()
            if not search_query:
                search_query = "유튜브"
            
            # 유튜브 검색 실행
            search_result = await mcp_client.call_tool("search_youtube_videos", {"query": search_query})
            
            if search_result and isinstance(search_result, dict) and 'content' in search_result:
                content = search_result['content']
                videos = []
                
                # 각 텍스트 항목을 JSON으로 파싱
                for item in content:
                    if item.get('type') == 'text':
                        try:
                            video_data = json.loads(item['text'])
                            videos.append(video_data)
                        except json.JSONDecodeError:
                            continue
                
                # 응답 생성
                response = f"'{search_query}'에 대한 검색 결과입니다:\n\n"
                for i, video in enumerate(videos[:5], 1):  # 상위 5개
                    response += f"{i}. **{video.get('title', 'N/A')}**\n"
                    response += f"   📺 채널: {video.get('channelName', 'N/A')}\n"
                    response += f"   👀 조회수: {video.get('viewCount', 0):,}\n"
                    response += f"   👍 좋아요: {video.get('likeCount', 0):,}\n"
                    response += f"   🔗 [영상 보기]({video.get('url', 'N/A')})\n\n"
                
                return response
            else:
                return "죄송합니다. 검색 결과를 가져올 수 없습니다."
        
        elif "자막" in user_message or "transcript" in user_message.lower():
            # URL 추출 (개선된 방법)
            import re
            url_pattern = r'https?://(?:www\.)?youtube\.com/watch\?v=[A-Za-z0-9_-]+|https?://youtu\.be/[A-Za-z0-9_-]+'
            urls = re.findall(url_pattern, user_message)
            
            if urls:
                url = urls[0]
                print(f"자막을 추출하는 중... URL: {url}")
                transcript_result = await mcp_client.call_tool("get_youtube_transcript", {"url": url})
                
                if transcript_result and isinstance(transcript_result, dict) and 'content' in transcript_result:
                    content = transcript_result['content']
                    if content and len(content) > 0 and 'text' in content[0]:
                        transcript_text = content[0]['text']
                        return f"**자막 내용 (처음 500자):**\n\n{transcript_text[:500]}..."
                    else:
                        return "자막을 가져올 수 없습니다."
                else:
                    return "자막을 가져올 수 없습니다."
            else:
                return "유튜브 URL을 제공해주세요. 예: https://www.youtube.com/watch?v=VIDEO_ID"
        
        else:
            return "안녕하세요! 유튜브 검색이나 자막 추출을 도와드릴 수 있습니다. 무엇을 도와드릴까요?"
    
    except Exception as e:
        return f"오류가 발생했습니다: {str(e)}"

# 메시지 처리
async def process_user_message():
    # MCP 클라이언트 설정
    mcp_client = await setup_mcp_servers()
    
    if not mcp_client:
        st.error("MCP 서버를 연결할 수 없습니다.")
        return

    # 마지막 사용자 메시지 가져오기
    if st.session_state.chat_history:
        last_message = st.session_state.chat_history[-1]
        if last_message["role"] == "user":
            user_input = last_message["content"]
            
            # AI 응답 생성
            response_text = await generate_response(user_input, mcp_client)
            
            # 응답을 채팅 기록에 추가
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": response_text
        })
        else:
            st.error("사용자 메시지를 찾을 수 없습니다.")
    else:
        st.error("채팅 기록이 없습니다.")

# Streamlit UI 메인
def main():
    st.set_page_config(page_title="유튜브 에이전트", page_icon="🎥")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    st.title("🎥 유튜브 컨텐츠 에이전트")
    st.caption("유튜브 검색과 자막 추출을 도와드립니다!")

    # 사이드바
    with st.sidebar:
        st.header("설정")
        
        if st.button("채팅 기록 초기화"):
            st.session_state.chat_history = []
            st.rerun()
        
        st.markdown("### 사용법")
        st.markdown("""
        - **검색**: "파이썬 강의 검색해줘"
        - **자막**: "이 영상의 자막 추출해줘 https://youtube.com/watch?v=..."
        """)

    # 채팅 기록 표시
    for m in st.session_state.chat_history:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    # 사용자 입력 처리
    user_input = st.chat_input("메시지를 입력하세요...")
    if user_input:
        # 사용자 메시지 추가
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # AI 응답 생성
        with st.chat_message("assistant"):
            with st.spinner("처리 중..."):
                try:
                    asyncio.run(process_user_message())
                    # 마지막 응답 표시
                    if st.session_state.chat_history:
                        last_response = st.session_state.chat_history[-1]
                        if last_response["role"] == "assistant":
                            st.markdown(last_response["content"])
        except Exception as e:
            st.error(f"처리 중 오류 발생: {str(e)}")
            st.session_state.chat_history.append({
                "role": "assistant", 
                "content": f"오류가 발생했습니다: {str(e)}"
            })

if __name__ == "__main__":
    main()