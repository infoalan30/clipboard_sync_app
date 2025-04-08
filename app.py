import streamlit as st
from streamlit.components.v1 import html
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
    try:
        tz = pytz.timezone(TARGET_TIMEZONE)
        return dt.replace(tzinfo=pytz.utc).astimezone(tz)
    except Exception as e:
        print(f"Error getting local time: {e}") # Log error
        return datetime.utcnow().replace(tzinfo=pytz.utc) # Fallback to UTC

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
    # Ensure keys always exist, even if None
    return {"data": None, "metadata": None, "timestamp": None}

def set_clipboard_data(data, metadata):
    """Stores data and metadata in the shared cache container."""
    try:
        container = get_cache_container()
        container["data"] = data
        container["metadata"] = metadata
        # Set timestamp only if data is actually set, clear it otherwise
        container["timestamp"] = time.time() if data is not None else None
        log_type = "Cleared" if data is None else (metadata.get('type', 'unknown') if metadata else 'unknown')
        print(f"[{datetime.now()}] Data set in cache: Type {log_type}")
        return True
    except Exception as e:
        st.error(f"Failed to set cache data: {e}")
        print(f"Error accessing cache container during set: {e}")
        return False

def get_clipboard_data():
    """Retrieves data and metadata from the shared cache container."""
    try:
        # Use .get() for safety, though @st.cache_resource should guarantee the dict structure
        container = get_cache_container()
        timestamp = container.get("timestamp")
        if timestamp is None:
             # Explicitly check timestamp, as data might persist briefly after TTL in some edge cases
             print(f"[{datetime.now()}] Cache miss or explicitly cleared (timestamp is None).")
             return None, None
        else:
             # Check TTL manually just in case resource TTL has slight delay in invalidation
             if time.time() > (timestamp + CACHE_TTL_SECONDS):
                 print(f"[{datetime.now()}] Cache expired (manual check).")
                 # Optionally clear the container explicitly here if needed,
                 # but cache_resource should handle invalidation.
                 # container["data"] = None
                 # container["metadata"] = None
                 # container["timestamp"] = None
                 return None, None # Treat as expired

             print(f"[{datetime.now()}] Cache hit. Timestamp (UTC): {datetime.utcfromtimestamp(timestamp)}")
             return container.get("data"), container.get("metadata") # Use .get() for safety

    except Exception as e:
        # Handle potential state where container is briefly None during creation/error
        if isinstance(e, AttributeError) and "'NoneType' object has no attribute 'get'" in str(e):
             print(f"[{datetime.now()}] Cache container likely not ready yet.")
             return None, None
        st.error(f"Failed to get cache data: {e}")
        print(f"Error accessing cache container during get: {e}")
        return None, None


# --- Security ---
def verify_api_key(provided_key):
    """Checks if the provided API key matches the one in secrets."""
    try:
        correct_key = st.secrets["API_KEY"]
        # Ensure comparison handles potential None inputs safely
        return bool(provided_key and provided_key == correct_key)
    except KeyError:
        if 'action' not in st.query_params:
             st.error("API_KEY not found in Streamlit secrets.")
        print("API_KEY not found in secrets.")
        return False
    except Exception as e:
        if 'action' not in st.query_params:
            st.error(f"Error verifying API key: {e}")
        print(f"Error verifying API key: {e}")
        return False

# --- API Handling (via Query Params) ---
def handle_api_request():
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

                if content_type == "text":
                    # Raw text output (best effort)
                    st.markdown(f"```\n{data}\n```")
                    st.stop()

                elif content_type in ["image", "file"]:
                    filename = metadata.get("filename", "downloaded_file")
                    mime_type = metadata.get("mime_type", "application/octet-stream")
                    st.write(f"Type: {content_type.capitalize()}")
                    st.write(f"Filename: {filename}")
                    st.write(f"MIME Type: {mime_type}")
                    st.write(f"Size: {format_size(len(data))}")

                    # --- Modification: Display image in API view ---
                    if content_type == "image":
                        try:
                            st.image(data, caption=f"Preview: {filename}")
                        except Exception as e:
                            st.warning(f"Could not display image preview: {e}")
                    # --- End Modification ---

                    st.download_button(
                        label=f"Download {filename}",
                        data=data,
                        file_name=filename,
                        mime=mime_type,
                        key="api_download_button"
                    )
                    st.caption("Note for automation: Download requires interacting with this page.")
                    st.stop()
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
handle_api_request() # Check for API requests first

st.title("☁️ Simple Clipboard Sync")
st.caption("Paste text and save it, or upload a file/image (saved automatically). Retrieve via API URL.")





# --- Live Clock Component using JavaScript ---
try:
    # Get the target timezone string from your configuration
    TARGET_TIMEZONE = "Asia/Shanghai" # Ensure this matches your config

    # Optional but recommended: Validate timezone using pytz
    try:
        pytz.timezone(TARGET_TIMEZONE)
        js_timezone_string = TARGET_TIMEZONE
    except pytz.UnknownTimeZoneError:
        st.warning(f"Invalid Timezone '{TARGET_TIMEZONE}' configured. Clock may show client's local time or UTC as fallback.")
        # Fallback for JS - using UTC is often safer than letting it guess wrongly
        js_timezone_string = "UTC"

    # Define the HTML structure and the JavaScript logic
    live_clock_html = f"""
    <div id="live-clock-container" style="font-size: 0.9em; color: grey; margin-bottom: 10px;">
        <span id="live-clock">Loading current time...</span>
    </div>

    <script>
        const clockElement = document.getElementById('live-clock');
        const targetTimezone = "{js_timezone_string}"; // Get timezone from Python

        function updateClock() {{
            try {{
                const now = new Date();
                // Options for formatting date and time in the target timezone
                const options = {{
                    timeZone: targetTimezone,
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: false // Use 24-hour format
                }};
                // Use Intl.DateTimeFormat for reliable cross-browser formatting
                const formatter = new Intl.DateTimeFormat(undefined, options); // 'undefined' uses client's locale for format style
                const formattedTime = formatter.format(now);

                // Update the HTML element
                clockElement.innerText = `🕒 Current Time ({targetTimezone}): ${formattedTime}`;

            }} catch (error) {{
                console.error("Error updating live clock:", error);
                clockElement.innerText = `Error displaying time for timezone: ${targetTimezone}`;
                // Stop updates if there's an error to prevent flooding console
                clearInterval(clockInterval);
            }}
        }}

        // Update the clock immediately when the script loads
        updateClock();

        // Set interval to update the clock every second (1000 milliseconds)
        const clockInterval = setInterval(updateClock, 1000);

        // Note: Streamlit components don't have a built-in 'unmount' cleanup hook
        // easily accessible here. The interval will technically keep running in the
        // background until the page is fully reloaded or closed. This is usually
        // not a major issue for a simple clock.

    </script>
    """

    # Embed the HTML/JS component into the Streamlit app
    st.components.v1.html(live_clock_html, height=35) # Adjust height as needed

except Exception as e:
    st.error(f"Failed to display live clock: {e}")








# try:
#     now_local = get_local_time()
#     st.write(f"🕒 Current Server Time ({TARGET_TIMEZONE}): {now_local.strftime('%Y-%m-%d %H:%M:%S')}")
# except Exception as e:
#     st.warning(f"Could not display local time: {e}")


st.markdown("---")

# Placeholders for status messages
upload_status_placeholder = st.empty()
clear_status_placeholder = st.empty()

# --- File Upload Handling ---
def handle_file_upload():
    # Check if the file uploader key exists and has a file
    if "file_uploader" in st.session_state and st.session_state.file_uploader is not None:
        uploaded_file = st.session_state.file_uploader
        filename = uploaded_file.name
        file_bytes = uploaded_file.getvalue()

        # --- Modification: Use placeholder for status ---
        with upload_status_placeholder, st.spinner(f"Saving '{filename}' to cloud cache..."):
            mime_type, _ = mimetypes.guess_type(filename)
            if mime_type is None: mime_type = "application/octet-stream"
            content_kind = "image" if mime_type.startswith("image/") else "file"
            metadata = {
                "type": content_kind, "filename": filename,
                "mime_type": mime_type, "original_size": uploaded_file.size,
            }
            if set_clipboard_data(file_bytes, metadata):
                # Clear previous message and show success
                upload_status_placeholder.success(f"{content_kind.capitalize()} '{filename}' saved to cache!")
                # We might need to clear the file uploader state to allow re-uploading the same file
                # This is tricky with on_change; often requires more complex state management
                # or letting the user manually clear it via the 'x'.
            else:
                 # Clear previous message and show error
                upload_status_placeholder.error(f"Failed to save {content_kind} '{filename}' to cache.")
    # else:
        # This part runs when the file is cleared via 'x' in the UI
        # Clear any previous status message when the file is removed
        # upload_status_placeholder.empty() # Let's not clear automatically, user might want to see last status
        # print("File uploader state changed, possibly cleared by user.")


col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Input Data Here:")
    st.file_uploader(
        "Upload Image/File (saves automatically)",
        type=None, key="file_uploader",
        on_change=handle_file_upload, # Callback handles saving and status
        accept_multiple_files=False
    )
    manual_text = st.text_area("Or Paste Text Here:", height=150, key="text_area")

with col2:
    st.subheader("Actions:")
    if st.button("💾 Save Text to Cloud Cache", key="save_text_button", use_container_width=True):
        text_to_save = st.session_state.text_area
        if text_to_save:
            metadata = {"type": "text"}
            if set_clipboard_data(text_to_save, metadata):
                st.success("Text saved to cache!") # Text save status can appear directly here
            else:
                st.error("Failed to save text to cache.")
        else:
            st.warning("Please paste text in the text area before saving.")

    if st.button("🗑️ Clear Cloud Cache", key="clear_button", use_container_width=True):
        # --- Modification: Use placeholder for clear status ---
        with clear_status_placeholder, st.spinner("Clearing cache..."):
            # Explicitly set timestamp to None when clearing
            if set_clipboard_data(None, None):
                 # Clear previous message and show success
                clear_status_placeholder.success("Cache cleared successfully.")
                # No need to rerun here, the next natural interaction or refresh will show empty cache.
                # st.rerun() # Rerun can sometimes cause race conditions or hide the success message
            else:
                 # Check if already empty
                 current_data, _ = get_clipboard_data()
                 if current_data is None and get_cache_container().get("timestamp") is None:
                     clear_status_placeholder.info("Cache is already empty or expired.")
                 else:
                     clear_status_placeholder.error("Failed to clear cache.")


st.markdown("---")

# --- Debugging Section ---
st.subheader("🛠️ Current Cache Content (for Debugging)")
st.caption(f"Cache automatically clears after {CACHE_TTL_SECONDS} seconds.")

# Get cache status
cached_data_debug, cached_metadata_debug = get_clipboard_data()
# Get timestamp directly ONLY if data is not None (more robust check)
timestamp_utc_float = get_cache_container().get("timestamp") if cached_data_debug is not None else None

if timestamp_utc_float:
    # Recalculate times based on potentially valid timestamp
    timestamp_utc = datetime.utcfromtimestamp(timestamp_utc_float)
    timestamp_local = get_local_time(timestamp_utc)
    expiry_time_utc = timestamp_utc + timedelta(seconds=CACHE_TTL_SECONDS)
    expiry_time_local = get_local_time(expiry_time_utc)
    time_left = expiry_time_utc - datetime.utcnow()

    # Check if expired based on time_left before displaying info
    if time_left.total_seconds() >= 0:
        st.info(f"Cache contains data stored at: {timestamp_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        st.info(f"Cache expires around: {expiry_time_local.strftime('%Y-%m-%d %H:%M:%S %Z')} (Time left: {format_timedelta(time_left)})")

        debug_api_key = st.text_input("Enter API Key to view cached content:", type="password", key="debug_api_key_input")
        if verify_api_key(debug_api_key):
            st.success("API Key Valid. Displaying content:")
            if cached_data_debug is not None and cached_metadata_debug is not None: # Redundant check, but safe
                data_type = cached_metadata_debug.get("type", "unknown")
                filename=cached_metadata_debug.get('filename', 'N/A')
                mime=cached_metadata_debug.get('mime_type', 'N/A')

                if data_type == "text":
                    st.write("**Type:** Text")
                    st.text(cached_data_debug)
                elif data_type == "image":
                     size=len(cached_data_debug)
                     st.write("**Type:** Image")
                     st.write(f"**Filename:** {filename}")
                     st.write(f"**MIME Type:** {mime}")
                     st.write(f"**Size:** {format_size(size)}")
                     try:
                         st.image(cached_data_debug, caption=filename)
                     except Exception as e:
                         st.error(f"Could not display image: {e}")
                     # Download button remains useful
                     st.download_button(label=f"Download {filename}", data=cached_data_debug, file_name=filename, mime=mime, key=f"debug_dl_img_{filename}")
                elif data_type == "file":
                     size=len(cached_data_debug)
                     st.write("**Type:** File")
                     st.write(f"**Filename:** {filename}")
                     st.write(f"**MIME Type:** {mime}")
                     st.write(f"**Size:** {format_size(size)}")
                     st.download_button(label=f"Download {filename}", data=cached_data_debug, file_name=filename, mime=mime, key=f"debug_dl_file_{filename}")
                else:
                    st.write("**Type:** Unknown")
                    st.write(cached_metadata_debug)
            else:
                 st.warning("Cache timestamp exists, but data/metadata seems missing now.")
        elif debug_api_key:
            st.error("Invalid API Key provided for debug view.")
    else:
        # If time_left calculation shows expired, display empty message
         st.info("Cache is currently empty or expired.")

else:
    # If timestamp was None initially
    st.info("Cache is currently empty or expired.")


# (API Access Info section remains the same)
st.markdown("---")
st.subheader("API Access")
st.write("To retrieve the data from another device/script, use a GET request to the following URL structure:")
try:
    from streamlit.web.server import Server
    server_address = Server.get_current()._get_server_address_for_client(include_path=False)
    app_url_guess = f"https://{server_address}" # Assuming HTTPS for cloud
    if "localhost" in server_address or "0.0.0.0" in server_address:
         app_url_guess = f"http://{server_address}" # Assuming HTTP for local
    st.code(f"{app_url_guess}?action=get_data&key=YOUR_API_KEY", language=None)
    st.caption("Note: Auto-detected URL might be incorrect. Use your app's public Streamlit Cloud URL.")
except Exception:
     st.code(f"YOUR_APP_URL?action=get_data&key=YOUR_API_KEY", language=None)
     st.caption("Replace `YOUR_APP_URL` with this app's public URL.")
st.write("Replace `YOUR_API_KEY` with the key configured in the Streamlit secrets.")
st.warning("""
**API Retrieval Notes:** Text is returned in a code block. Files/Images return a page with a download button and potentially an image preview. Direct raw file download via simple GET is not supported.
""")
