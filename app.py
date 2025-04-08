import streamlit as st
import time
from datetime import datetime, timedelta
import io
import mimetypes # To guess file type
import pytz # For timezone handling
from pathlib import Path # For safer filename handling

# --- Configuration ---
CACHE_TTL_SECONDS = 300 # 5 minutes
TARGET_TIMEZONE = "Asia/Shanghai" # Or choose another like "UTC", "America/New_York" etc.

# --- Helper Functions ---
def get_local_time(dt=None):
    """Converts UTC datetime to the target timezone."""
    if dt is None:
        dt = datetime.utcnow()
    tz = pytz.timezone(TARGET_TIMEZONE)
    return dt.replace(tzinfo=pytz.utc).astimezone(tz)

def format_timedelta(td):
    """Formats timedelta into H:M:S or M:S."""
    total_seconds = int(td.total_seconds())
    if total_seconds < 0:
        return "Expired"
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours:01}:{minutes:02}:{seconds:02}"
    else:
        return f"{minutes:02}:{seconds:02}"

def format_size(size_bytes):
    """Formats bytes into KB or MB."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{round(size_bytes / 1024)} KB"
    else:
        return f"{round(size_bytes / (1024 * 1024), 1)} MB"

# --- Cache Management using st.cache_resource ---
@st.cache_resource(ttl=CACHE_TTL_SECONDS)
def get_cache_container():
    print(f"[{datetime.now()}] Creating/Recreating cache container.")
    return {"data": None, "metadata": None, "timestamp": None}

def set_clipboard_data(data, metadata):
    """Stores data and metadata in the shared cache container."""
    try:
        container = get_cache_container()
        container["data"] = data
        container["metadata"] = metadata
        container["timestamp"] = time.time() # Store UTC timestamp
        # Log safely
        log_type = "Cleared" if data is None else (metadata.get('type', 'unknown') if metadata else 'unknown')
        print(f"[{datetime.now()}] Data set in cache: Type {log_type}")
        return True
    except Exception as e:
        st.error(f"Failed to set cache data: {e}")
        # If the container doesn't exist (shouldn't happen with cache_resource unless error)
        print(f"Error accessing cache container during set: {e}")
        return False

def get_clipboard_data():
    """Retrieves data and metadata from the shared cache container."""
    try:
        container = get_cache_container()
        if container.get("timestamp") is None: # Check existence using .get()
             print(f"[{datetime.now()}] Cache miss or empty.")
             return None, None
        else:
             print(f"[{datetime.now()}] Cache hit. Timestamp (UTC): {datetime.utcfromtimestamp(container['timestamp'])}")
             # TTL is handled by @st.cache_resource
             return container["data"], container["metadata"]
    except Exception as e:
        # Added specific check for the initial state if cache_resource fails temporarily
        if isinstance(e, TypeError) and "'NoneType' object is not subscriptable" in str(e):
             print(f"[{datetime.now()}] Cache container not yet initialized or error state.")
             return None, None
        st.error(f"Failed to get cache data: {e}")
        print(f"Error accessing cache container during get: {e}")

        return None, None


# --- Security ---
def verify_api_key(provided_key):
    """Checks if the provided API key matches the one in secrets."""
    try:
        correct_key = st.secrets["API_KEY"]
        if provided_key and provided_key == correct_key:
            return True
        else:
            return False
    except KeyError:
        # Avoid showing error repeatedly in API mode, just return False
        if 'action' not in st.query_params:
             st.error("API_KEY not found in Streamlit secrets. Please configure secrets.toml or Streamlit Cloud secrets.")
        print("API_KEY not found in secrets.")
        return False
    except Exception as e:
        if 'action' not in st.query_params:
            st.error(f"Error verifying API key: {e}")
        print(f"Error verifying API key: {e}")
        return False

# --- API Handling (via Query Params) ---
def handle_api_request():
    """Checks query params and handles API requests."""
    query_params = st.query_params

    if "action" in query_params and query_params["action"] == "get_data":
        api_key = query_params.get("key")
        if not api_key:
            st.error("API Error: Missing 'key' parameter.")
            st.stop()

        if verify_api_key(api_key):
            data, metadata = get_clipboard_data()

            if data is not None and metadata is not None:
                content_type = metadata.get("type")

                # --- Raw Output for API ---
                if content_type == "text":
                    # Try to output only the raw text
                    st.markdown(f"```\n{data}\n```") # Use markdown code block for plain text display
                    st.stop() # Stop execution to avoid rendering UI

                elif content_type in ["image", "file"]:
                     filename = metadata.get("filename", "downloaded_file")
                     mime_type = metadata.get("mime_type", "application/octet-stream")
                     # For files/images, we still need the download button mechanism.
                     # Outputting raw bytes directly isn't feasible in standard Streamlit response.
                     # Provide the download button as the primary way to get the file.
                     st.write(f"Type: {content_type.capitalize()}")
                     st.write(f"Filename: {filename}")
                     st.write(f"MIME Type: {mime_type}")
                     st.write(f"Size: {format_size(len(data))}")
                     st.download_button(
                         label=f"Download {filename}",
                         data=data,
                         file_name=filename,
                         mime=mime_type,
                         key="api_download_button"
                     )
                     # Add explanation for automation tools
                     st.caption("Note for automation: Streamlit serves this file via a dynamically generated link within this HTML page. Direct raw byte download via simple GET request is not supported. You may need tools that can interact with web pages (like Selenium) or parse the download link from this page's HTML source.")
                     st.stop() # Stop execution
                else:
                    st.warning("Unknown data type in cache.")
                    st.stop()
            else:
                st.info("API Key Valid, but no data currently in cache (or cache expired).")
                st.stop()
        else:
            st.error("API Error: Invalid API Key.")
            st.stop()

# --- Main App UI ---
st.set_page_config(layout="wide")

# --- Handle API request FIRST ---
handle_api_request() # If it's an API request, it will st.stop() here.

# --- If not an API request, show the normal UI ---
st.title("☁️ Simple Clipboard Sync")
st.caption("Paste text and save it, or upload a file/image (saved automatically). Retrieve via API URL.")

# Display current time (updates on interaction/rerun)
try:
    now_local = get_local_time()
    st.write(f"🕒 Current Server Time ({TARGET_TIMEZONE}): {now_local.strftime('%Y-%m-%d %H:%M:%S')}")
except Exception as e:
    st.warning(f"Could not display local time: {e}")

st.markdown("---")

# --- File Upload Handling (using session state and on_change) ---
def handle_file_upload():
    if "file_uploader" in st.session_state and st.session_state.file_uploader is not None:
        uploaded_file = st.session_state.file_uploader
        filename = uploaded_file.name
        file_bytes = uploaded_file.getvalue()

        with st.spinner(f"Saving '{filename}' to cloud cache..."):
            # Guess MIME type
            mime_type, _ = mimetypes.guess_type(filename)
            if mime_type is None:
                mime_type = "application/octet-stream" # Default if unknown

            content_kind = "file"
            if mime_type.startswith("image/"):
                 content_kind = "image"

            metadata = {
                "type": content_kind,
                "filename": filename,
                "mime_type": mime_type,
                "original_size": uploaded_file.size,
            }
            if set_clipboard_data(file_bytes, metadata):
                st.success(f"{content_kind.capitalize()} '{filename}' saved to cache!")
                # Clear the uploader state after successful save to allow re-uploading the same file
                # This might cause a rerun, which is often desired.
                # st.session_state.file_uploader = None # This might clear too early if rerun happens mid-way
                # Consider just letting it be, or using a more complex state management if needed
            else:
                st.error(f"Failed to save {content_kind} '{filename}' to cache.")
    # else:
        # This callback also triggers when the file is *removed* by the user clicking 'x'
        # print("File uploader state changed, possibly cleared.")


col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Input Data Here:")
    # File uploader triggers save on_change
    st.file_uploader(
        "Upload Image/File (saves automatically)",
        type=None,
        key="file_uploader", # Key is needed for session_state access
        on_change=handle_file_upload,
        accept_multiple_files=False # Ensure only one file
    )
    manual_text = st.text_area("Or Paste Text Here:", height=150, key="text_area")

with col2:
    st.subheader("Actions:")
    # Save button now only handles text
    if st.button("💾 Save Text to Cloud Cache", key="save_text_button", use_container_width=True):
        text_to_save = st.session_state.text_area # Get text from state
        if text_to_save:
            metadata = {"type": "text"}
            if set_clipboard_data(text_to_save, metadata):
                st.success("Text saved to cache!")
                # Optionally clear text area after save
                # st.session_state.text_area = "" # Requires rerun or careful state handling
            else:
                st.error("Failed to save text to cache.")
        else:
            st.warning("Please paste text in the text area before saving.")

    # Clear Cache Button
    if st.button("🗑️ Clear Cloud Cache", key="clear_button", use_container_width=True):
        with st.spinner("Clearing cache..."):
            # Clearing involves setting data and metadata to None
            if set_clipboard_data(None, None):
                st.success("Cache cleared.")
                 # Rerun to update debug section immediately
                st.rerun()
            else:
                # Added check for already empty case
                current_data, _ = get_clipboard_data()
                if current_data is None:
                     st.info("Cache is already empty or expired.")
                else:
                     st.error("Failed to clear cache.")


st.markdown("---")

# --- Debugging Section ---
st.subheader("🛠️ Current Cache Content (for Debugging)")
st.caption(f"Cache automatically clears after {CACHE_TTL_SECONDS} seconds.")

# Get cache status without revealing content yet
cached_data_debug, cached_metadata_debug = get_clipboard_data()
container_debug = get_cache_container() # Get the raw container for timestamp
timestamp_utc_float = container_debug.get("timestamp")

if timestamp_utc_float:
    timestamp_utc = datetime.utcfromtimestamp(timestamp_utc_float)
    timestamp_local = get_local_time(timestamp_utc)
    expiry_time_utc = timestamp_utc + timedelta(seconds=CACHE_TTL_SECONDS)
    expiry_time_local = get_local_time(expiry_time_utc)
    time_left = expiry_time_utc - datetime.utcnow() # Calculate diff in UTC

    st.info(f"Cache contains data stored at: {timestamp_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    st.info(f"Cache expires around: {expiry_time_local.strftime('%Y-%m-%d %H:%M:%S %Z')} (Time left: {format_timedelta(time_left)})")

    # Ask for API Key to show content
    debug_api_key = st.text_input("Enter API Key to view cached content:", type="password", key="debug_api_key_input")
    if verify_api_key(debug_api_key):
        st.success("API Key Valid. Displaying content:")
        if cached_data_debug is not None and cached_metadata_debug is not None:
            data_type = cached_metadata_debug.get("type", "unknown")

            if data_type == "text":
                st.write("**Type:** Text")
                st.text(cached_data_debug)
            elif data_type == "image":
                filename=cached_metadata_debug.get('filename', 'N/A')
                mime=cached_metadata_debug.get('mime_type', 'N/A')
                size=len(cached_data_debug)
                st.write("**Type:** Image")
                st.write(f"**Filename:** {filename}")
                st.write(f"**MIME Type:** {mime}")
                st.write(f"**Size:** {format_size(size)}")
                try:
                    st.image(cached_data_debug, caption=filename)
                    # Add download button next to image
                    st.download_button(
                        label=f"Download {filename}",
                        data=cached_data_debug,
                        file_name=filename,
                        mime=mime,
                        key=f"debug_download_{filename}" # Unique key
                    )
                except Exception as e:
                    st.error(f"Could not display image: {e}. Providing download link instead.")
                    st.download_button(
                        label=f"Download {filename}",
                        data=cached_data_debug,
                        file_name=filename,
                        mime=mime,
                        key=f"debug_download_err_{filename}" # Unique key
                    )
            elif data_type == "file":
                filename=cached_metadata_debug.get('filename', 'N/A')
                mime=cached_metadata_debug.get('mime_type', 'N/A')
                size=len(cached_data_debug)
                st.write("**Type:** File")
                st.write(f"**Filename:** {filename}")
                st.write(f"**MIME Type:** {mime}")
                st.write(f"**Size:** {format_size(size)}")
                st.download_button(
                    label=f"Download {filename}",
                    data=cached_data_debug,
                    file_name=filename,
                    mime=mime,
                    key=f"debug_download_file_{filename}" # Unique key
                )
            else:
                st.write("**Type:** Unknown")
                st.write("Cached data exists but its type is unclear.")
                st.write(cached_metadata_debug)
        else:
             # This case shouldn't happen if timestamp exists, but good to handle
             st.warning("Cache timestamp exists, but data/metadata is missing. Cache might be in an inconsistent state.")

    elif debug_api_key: # Only show if key was entered but invalid
        st.error("Invalid API Key provided for debug view.")

else:
    st.info("Cache is currently empty or expired.")

st.markdown("---")
st.subheader("API Access")
st.write("To retrieve the data from another device/script, use a GET request to the following URL structure:")
# Dynamically try to get the server address (works better locally than on cloud)
try:
    from streamlit.web.server import Server
    # This is an internal API and might break in future Streamlit versions
    server_address = Server.get_current()._get_server_address_for_client(include_path=False)
    # Sometimes includes port, sometimes not. Needs careful handling.
    # Usually on cloud, you know the *.streamlit.app URL.
    app_url_guess = f"https://{server_address}" # Assuming HTTPS for cloud
    if "localhost" in server_address or "0.0.0.0" in server_address:
         app_url_guess = f"http://{server_address}" # Assuming HTTP for local
    st.code(f"{app_url_guess}?action=get_data&key=YOUR_API_KEY", language=None)
    st.caption("Note: The auto-detected URL might be incorrect, especially on Cloud. Please use your app's public Streamlit Cloud URL (e.g., https://your-app-name.streamlit.app).")
except Exception:
     st.code(f"YOUR_APP_URL?action=get_data&key=YOUR_API_KEY", language=None)
     st.caption("Replace `YOUR_APP_URL` with this app's public URL on Streamlit Cloud.")

st.write("Replace `YOUR_API_KEY` with the key configured in the Streamlit secrets.")
st.warning("""
**API Retrieval Notes:**
*   **Text:** The API endpoint attempts to return plain text within a code block. Automation tools might need to parse this from the HTML response.
*   **Files/Images:** The API endpoint returns an HTML page containing a download button. Direct raw file download via a simple GET request is **not** supported by this Streamlit implementation. You would need a tool that can interact with the web page (like Selenium) or parse the download link from the HTML source.
*   **Security:** The API key is sent as a URL query parameter. Use this method only for temporary, non-critical data and ensure your app uses HTTPS (default on Streamlit Cloud).
""")
