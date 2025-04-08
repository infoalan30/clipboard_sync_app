import streamlit as st
import time
from datetime import datetime, timedelta
import io
import mimetypes # To guess file type

# --- Configuration ---
CACHE_TTL_SECONDS = 300 # 5 minutes

# --- Cache Management using st.cache_resource ---
# This creates a dictionary-like object that persists across reruns
# and sessions for the duration of the TTL. Modifications to the
# returned dictionary are reflected for all users viewing the cache
# until it expires.
@st.cache_resource(ttl=CACHE_TTL_SECONDS)
def get_cache_container():
    print(f"[{datetime.now()}] Creating/Recreating cache container.") # For debugging TTL expiry
    # The container holds the actual data and metadata
    return {"data": None, "metadata": None, "timestamp": None}

def set_clipboard_data(data, metadata):
    """Stores data and metadata in the shared cache container."""
    try:
        container = get_cache_container()
        container["data"] = data
        container["metadata"] = metadata
        container["timestamp"] = time.time()
        # Force Streamlit to recognize the container has changed (might not always be needed, but safer)
        # st.experimental_rerun() # Let's see if it works without explicit rerun first
        print(f"[{datetime.now()}] Data set in cache: Type {metadata.get('type')}")
        return True
    except Exception as e:
        st.error(f"Failed to set cache data: {e}")
        return False

def get_clipboard_data():
    """Retrieves data and metadata from the shared cache container."""
    try:
        container = get_cache_container()
        # Check if the container was just created (data is None) or if it holds old data
        if container["timestamp"] is None:
             print(f"[{datetime.now()}] Cache miss or empty.")
             return None, None # No valid data
        else:
             print(f"[{datetime.now()}] Cache hit. Timestamp: {datetime.fromtimestamp(container['timestamp'])}")
             # No need for manual time check, TTL handles expiry.
             # If get_cache_container() didn't raise an error or reset, the data is valid.
             return container["data"], container["metadata"]
    except Exception as e:
        st.error(f"Failed to get cache data: {e}")
        return None, None


# --- Security ---
def verify_api_key(provided_key):
    """Checks if the provided API key matches the one in secrets."""
    try:
        # Access the secret stored in Streamlit Cloud Secrets (secrets.toml)
        correct_key = st.secrets["API_KEY"]
        if provided_key and provided_key == correct_key:
            return True
        else:
            return False
    except KeyError:
        st.error("API_KEY not found in Streamlit secrets. Please configure secrets.toml.")
        return False
    except Exception as e:
        st.error(f"Error verifying API key: {e}")
        return False

# --- API Handling (via Query Params) ---
def handle_api_request():
    """Checks query params and handles API requests."""
    query_params = st.query_params

    if "action" in query_params and query_params["action"] == "get_data":
        api_key = query_params.get("key")
        if not api_key:
            st.error("API Error: Missing 'key' parameter.")
            st.stop() # Stop execution for this request

        if verify_api_key(api_key):
            # Key is valid, attempt to retrieve data
            data, metadata = get_clipboard_data()

            if data is not None and metadata is not None:
                st.success("API Key Valid. Data retrieved from cache.")
                content_type = metadata.get("type")

                if content_type == "text":
                    st.write("Type: Text")
                    # Displaying as plain text might be best for API usage
                    st.code(data, language=None)
                    # Alternative: st.text(data)

                elif content_type in ["image", "file"]:
                    filename = metadata.get("filename", "downloaded_file")
                    mime_type = metadata.get("mime_type", "application/octet-stream")
                    st.write(f"Type: {content_type.capitalize()}")
                    st.write(f"Filename: {filename}")
                    st.write(f"MIME Type: {mime_type}")
                    st.write(f"Size: {len(data)} bytes")
                    # Provide download button - direct raw download isn't feasible easily
                    st.download_button(
                        label=f"Download {filename}",
                        data=data,
                        file_name=filename,
                        mime=mime_type,
                    )
                else:
                    st.warning("Unknown data type in cache.")

            else:
                st.info("API Key Valid, but no data currently in cache (or cache expired).")

        else:
            st.error("API Error: Invalid API Key.")

        # Stop further execution after handling the API request
        st.stop()

# --- Main App UI ---
st.set_page_config(layout="wide")

# --- Handle API request FIRST ---
handle_api_request() # If it's an API request, it will st.stop() here.

# --- If not an API request, show the normal UI ---
st.title("☁️ Simple Clipboard Sync")
st.caption("Paste text or upload a file/image, save it, then retrieve it from another device via the API URL.")
st.markdown("---")

col1, col2 = st.columns([2, 1]) # Input column wider than button column

with col1:
    st.subheader("Input Data Here:")
    # Priority: File Uploader > Text Area if both have content? Let user decide via button click.
    uploaded_file = st.file_uploader("Upload an Image or File", type=None, key="file_uploader") # Accept any type
    manual_text = st.text_area("Or Paste Text Here:", height=150, key="text_area")

with col2:
    st.subheader("Actions:")
    if st.button("💾 Save to Cloud Cache", key="save_button", use_container_width=True):
        saved = False
        # Prioritize uploaded file if present
        if uploaded_file is not None:
            file_bytes = uploaded_file.getvalue()
            filename = uploaded_file.name
            # Guess MIME type
            mime_type, _ = mimetypes.guess_type(filename)
            if mime_type is None:
                mime_type = "application/octet-stream" # Default if unknown

            # Basic check if it's likely an image for metadata purposes
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
                saved = True
            else:
                st.error(f"Failed to save {content_kind} to cache.")

        # If no file was uploaded OR file saving failed, check text area
        elif manual_text:
            metadata = {"type": "text"}
            if set_clipboard_data(manual_text, metadata):
                st.success("Text saved to cache!")
                saved = True
            else:
                st.error("Failed to save text to cache.")

        else:
            st.warning("Please provide text or upload a file before saving.")

        # Clear inputs after successful save
        if saved:
            # Resetting widgets requires rerunning the script.
            # We can clear session state values if we used them, or just let them be.
            # For file_uploader, setting it to None might require more complex state management.
            # Usually, after a button click, Streamlit reruns, and inputs might reset
            # depending on how keys are handled. Let's see default behavior.
            # If inputs don't clear, uncommenting the rerun might help, or using session_state.
            # st.experimental_rerun()
            pass


    # Optional: Add a button to explicitly clear the cache
    if st.button("🗑️ Clear Cloud Cache", key="clear_button", use_container_width=True):
        # To clear a resource cache, we might need to manipulate internal state or
        # simply overwrite with None. Let's try overwriting.
        if set_clipboard_data(None, None):
            st.success("Cache cleared.")
        else:
            st.error("Failed to clear cache (it might already be empty or expired).")


st.markdown("---")

# --- Debugging Section ---
st.subheader("🛠️ Current Cache Content (for Debugging)")
st.caption(f"Cache automatically clears after {CACHE_TTL_SECONDS} seconds of inactivity.")

cached_data, cached_metadata = get_clipboard_data()

if cached_data is not None and cached_metadata is not None:
    data_type = cached_metadata.get("type", "unknown")
    timestamp = get_cache_container()["timestamp"] # Get the timestamp directly
    expiry_time = datetime.fromtimestamp(timestamp + CACHE_TTL_SECONDS)
    time_left = expiry_time - datetime.now()

    st.info(f"Cache contains data stored at: {datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')}")
    st.info(f"Cache expires around: {expiry_time.strftime('%Y-%m-%d %H:%M:%S')} (Time left: {max(timedelta(0), time_left)})")


    if data_type == "text":
        st.write("**Type:** Text")
        st.text(cached_data)
    elif data_type == "image":
        st.write("**Type:** Image")
        st.write(f"**Filename:** {cached_metadata.get('filename', 'N/A')}")
        st.write(f"**MIME Type:** {cached_metadata.get('mime_type', 'N/A')}")
        try:
            st.image(cached_data, caption=cached_metadata.get('filename', 'Cached Image'))
        except Exception as e:
            st.error(f"Could not display image: {e}. Providing download link instead.")
            st.download_button(
                label=f"Download {cached_metadata.get('filename', 'image_file')}",
                data=cached_data,
                file_name=cached_metadata.get('filename', 'image_file'),
                mime=cached_metadata.get('mime_type', 'application/octet-stream')
            )
    elif data_type == "file":
        st.write("**Type:** File")
        st.write(f"**Filename:** {cached_metadata.get('filename', 'N/A')}")
        st.write(f"**MIME Type:** {cached_metadata.get('mime_type', 'N/A')}")
        st.write(f"**Size:** {len(cached_data)} bytes")
        st.download_button(
            label=f"Download {cached_metadata.get('filename', 'cached_file')}",
            data=cached_data,
            file_name=cached_metadata.get('filename', 'cached_file'),
            mime=cached_metadata.get('mime_type', 'application/octet-stream')
        )
    else:
        st.write("**Type:** Unknown")
        st.write("Cached data exists but its type is unclear.")
        st.write(cached_metadata) # Show metadata for debugging

else:
    st.info("Cache is currently empty or expired.")

st.markdown("---")
st.subheader("API Access")
st.write("To retrieve the data from another device/script, use a GET request to the following URL structure:")
# Dynamically get the app's base URL (this part is tricky/might not be reliable)
# For deployed apps, you know the URL. For local, it's usually localhost:8501
st.code(f"YOUR_APP_URL?action=get_data&key=YOUR_API_KEY", language=None)
st.write("Replace `YOUR_APP_URL` with this app's public URL on Streamlit Cloud.")
st.write("Replace `YOUR_API_KEY` with the key configured in the Streamlit secrets.")
st.warning("Note: The API key is sent as a query parameter, which is visible in server logs and potentially browser history. Use this for temporary, non-critical data only. Ensure the app is served over HTTPS (default on Streamlit Cloud).")
