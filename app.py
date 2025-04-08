import streamlit as st
import streamlit.components.v1 as components
import time
import base64
from datetime import datetime, timedelta
import requests
from io import BytesIO

# 缓存数据结构
if "clipboard_data" not in st.session_state:
    st.session_state.clipboard_data = {
        "content": None,
        "type": None,
        "timestamp": None
    }

# 密钥（从Streamlit Secrets获取）
API_KEY = st.secrets.get("API_KEY", "default_key")  # 默认值仅用于本地测试

# 清理缓存（每5分钟）
def clean_cache():
    if st.session_state.clipboard_data["timestamp"]:
        if datetime.now() > st.session_state.clipboard_data["timestamp"] + timedelta(minutes=5):
            st.session_state.clipboard_data = {"content": None, "type": None, "timestamp": None}

# JavaScript代码：读取剪切板
CLIPBOARD_JS = """
<script>
async function copyClipboard() {
    try {
        const text = await navigator.clipboard.readText();
        if (text) {
            window.parent.postMessage({type: 'text', content: text}, '*');
            return;
        }
        const clipboardItems = await navigator.clipboard.read();
        for (const item of clipboardItems) {
            for (const type of item.types) {
                const blob = await item.getType(type);
                const reader = new FileReader();
                reader.onload = function(event) {
                    window.parent.postMessage({type: type, content: event.target.result}, '*');
                };
                reader.readAsDataURL(blob);
            }
        }
    } catch (err) {
        console.error('Failed to read clipboard:', err);
    }
}
</script>
<button onclick="copyClipboard()">Copy Clipboard</button>
"""

# 主界面
st.title("Clipboard Sync App")

# 按钮和剪切板读取
components.html(CLIPBOARD_JS, height=100)

# 处理JavaScript传回的数据
if "message" in st.session_state:
    data = st.session_state.message
    st.session_state.clipboard_data = {
        "content": data["content"],
        "type": data["type"],
        "timestamp": datetime.now()
    }
    del st.session_state.message  # 清理临时数据

# 显示当前剪切板内容
clean_cache()  # 检查并清理缓存
if st.session_state.clipboard_data["content"]:
    if st.session_state.clipboard_data["type"] == "text":
        st.write("Text:", st.session_state.clipboard_data["content"])
    elif st.session_state.clipboard_data["type"].startswith("image"):
        st.image(st.session_state.clipboard_data["content"])
    elif st.session_state.clipboard_data["type"].startswith("video"):
        st.video(st.session_state.clipboard_data["content"])

# API端点（模拟实现）
def api_endpoint():
    query_key = st.experimental_get_query_params().get("key", [""])[0]
    if query_key != API_KEY:
        return {"error": "Invalid API key"}, 403
    
    clean_cache()
    if not st.session_state.clipboard_data["content"]:
        return {"error": "No content available"}, 404
    
    return {
        "type": st.session_state.clipboard_data["type"],
        "content": st.session_state.clipboard_data["content"],
        "timestamp": st.session_state.clipboard_data["timestamp"].isoformat()
    }, 200

# 模拟API调用（实际部署后通过URL访问）
if st.button("Test API"):
    response, status = api_endpoint()
    st.json(response)

# 说明如何访问API
st.write(f"API Endpoint: {st.experimental_get_query_params().get('url', ['https://your-app.streamlit.app'])[0]}/?key={API_KEY}")
