import streamlit as st
import pandas as pd
import asyncio
import os
import tempfile
from telethon import TelegramClient
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.types import InputPhoneContact
from telethon.errors import SessionPasswordNeededError, FloodWaitError
import time
import nest_asyncio

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

# Set page config
st.set_page_config(
    page_title="Telegram User Finder",
    page_icon="📱",
    layout="wide"
)

st.title("📱 Telegram User Finder")
st.markdown("Find which phone numbers from your Excel file have Telegram accounts")

# Initialize session state
if 'client' not in st.session_state:
    st.session_state.client = None
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'phone_numbers' not in st.session_state:
    st.session_state.phone_numbers = []
if 'found_users' not in st.session_state:
    st.session_state.found_users = []
if 'event_loop' not in st.session_state:
    st.session_state.event_loop = None
if 'auth_step' not in st.session_state:
    st.session_state.auth_step = 'start'  # start, code_sent, password_needed, authenticated

def get_or_create_event_loop():
    """Get the current event loop or create a new one"""
    if st.session_state.event_loop is None:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("Event loop is closed")
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        st.session_state.event_loop = loop
    return st.session_state.event_loop

# Helper function to clean phone numbers
def clean_phone_numbers(df, column_name):
    """Extract and clean mobile numbers, convert to +91 format"""
    try:
        raw_numbers = df[column_name].astype(str)
        phone_numbers = []
        for num in raw_numbers:
            digits_only = ''.join(filter(str.isdigit, num))
            if len(digits_only) >= 10:
                phone_numbers.append('+91' + digits_only[-10:])
        return phone_numbers
    except Exception as e:
        st.error(f"Error processing phone numbers: {str(e)}")
        return []

# Step 1: API Configuration
st.header("1. 🔐 API Configuration")
col1, col2 = st.columns(2)

with col1:
    api_id = st.text_input("API ID", help="Your Telegram API ID")
    phone_number = st.text_input("Phone Number", placeholder="+1234567890", help="Your phone number with country code")

with col2:
    api_hash = st.text_input("API Hash", type="password", help="Your Telegram API Hash")

# Step 2: File Upload
st.header("2. 📁 Upload Excel File")
uploaded_file = st.file_uploader(
    "Choose your Excel file containing phone numbers",
    type=['xlsx', 'xls'],
    help="Excel file should contain a column with mobile numbers"
)

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)
        st.success(f"✅ File uploaded successfully! Found {len(df)} rows")
        
        # Show preview
        st.subheader("Preview of uploaded data:")
        st.dataframe(df.head())
        
        # Column selection
        columns = df.columns.tolist()
        selected_column = st.selectbox(
            "Select the column containing mobile numbers:",
            columns,
            help="Choose which column contains the phone numbers"
        )
        
        if selected_column:
            # Process phone numbers
            st.session_state.phone_numbers = clean_phone_numbers(df, selected_column)
            st.info(f"📱 Processed {len(st.session_state.phone_numbers)} valid phone numbers")
            
            # Show sample of processed numbers
            if st.session_state.phone_numbers:
                with st.expander("View processed phone numbers (first 10)"):
                    for i, num in enumerate(st.session_state.phone_numbers[:10]):
                        st.text(f"{i+1}. {num}")
                    if len(st.session_state.phone_numbers) > 10:
                        st.text(f"... and {len(st.session_state.phone_numbers) - 10} more")
    
    except Exception as e:
        st.error(f"❌ Error reading file: {str(e)}")

# Step 3: Authentication
if api_id and api_hash and phone_number and st.session_state.phone_numbers:
    st.header("3. 🔒 Telegram Authentication")
    
    if st.session_state.auth_step == 'start':
        if st.button("🚀 Start Authentication", type="primary"):
            try:
                # Create session file in temp directory
                session_name = f"session_{int(time.time())}"
                
                # Initialize client
                st.session_state.client = TelegramClient(session_name, int(api_id), api_hash)
                
                with st.spinner("Connecting to Telegram..."):
                    async def start_auth():
                        await st.session_state.client.connect()
                        if not await st.session_state.client.is_user_authorized():
                            await st.session_state.client.send_code_request(phone_number)
                            return False
                        return True
                    
                    # Use consistent event loop
                    loop = get_or_create_event_loop()
                    is_authorized = loop.run_until_complete(start_auth())
                    
                    if is_authorized:
                        st.session_state.authenticated = True
                        st.session_state.auth_step = 'authenticated'
                        st.success("✅ Already authenticated!")
                        st.rerun()
                    else:
                        st.session_state.auth_step = 'code_sent'
                        st.info("📱 Verification code sent to your Telegram app")
                        st.rerun()
                        
            except Exception as e:
                st.error(f"❌ Authentication error: {str(e)}")
                st.session_state.auth_step = 'start'
    
    # OTP Input
    elif st.session_state.auth_step == 'code_sent':
        st.info("📱 Please enter the verification code sent to your Telegram app")
        otp_code = st.text_input("Enter the verification code:", max_chars=5, key="otp_input")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("✅ Verify Code", disabled=not otp_code or len(otp_code) != 5):
                try:
                    with st.spinner("Verifying code..."):
                        async def verify_code():
                            try:
                                await st.session_state.client.sign_in(phone_number, otp_code)
                                return True, None
                            except SessionPasswordNeededError:
                                return False, "password_needed"
                            except Exception as e:
                                return False, str(e)
                        
                        # Use same event loop
                        loop = get_or_create_event_loop()
                        success, error = loop.run_until_complete(verify_code())
                        
                        if success:
                            st.session_state.authenticated = True
                            st.session_state.auth_step = 'authenticated'
                            st.success("✅ Successfully authenticated!")
                            st.rerun()
                        elif error == "password_needed":
                            st.session_state.auth_step = 'password_needed'
                            st.info("🔐 Two-factor authentication enabled. Please enter your password.")
                            st.rerun()
                        else:
                            st.error(f"❌ Verification failed: {error}")
                            
                except Exception as e:
                    st.error(f"❌ Error during verification: {str(e)}")
        
        with col2:
            if st.button("🔄 Resend Code"):
                try:
                    async def resend_code():
                        await st.session_state.client.send_code_request(phone_number)
                    
                    loop = get_or_create_event_loop()
                    loop.run_until_complete(resend_code())
                    st.success("📱 New verification code sent!")
                except Exception as e:
                    st.error(f"❌ Error resending code: {str(e)}")
    
    # Password Input (for 2FA)
    elif st.session_state.auth_step == 'password_needed':
        st.info("🔐 Two-factor authentication is enabled for your account")
        password = st.text_input("Enter your 2FA password:", type="password", key="password_input")
        
        if st.button("🔓 Verify Password", disabled=not password):
            try:
                with st.spinner("Verifying password..."):
                    async def verify_password():
                        await st.session_state.client.sign_in(password=password)
                    
                    # Use same event loop
                    loop = get_or_create_event_loop()
                    loop.run_until_complete(verify_password())
                    st.session_state.authenticated = True
                    st.session_state.auth_step = 'authenticated'
                    st.success("✅ Successfully authenticated with 2FA!")
                    st.rerun()
                    
            except Exception as e:
                st.error(f"❌ Password verification failed: {str(e)}")
    
    elif st.session_state.auth_step == 'authenticated':
        st.success("✅ Successfully authenticated with Telegram!")
        if st.button("🔄 Reset Authentication"):
            st.session_state.auth_step = 'start'
            st.session_state.authenticated = False
            if st.session_state.client:
                try:
                    async def disconnect():
                        await st.session_state.client.disconnect()
                    loop = get_or_create_event_loop()
                    loop.run_until_complete(disconnect())
                except:
                    pass
                st.session_state.client = None
            st.rerun()

# Step 4: Find Telegram Users
if st.session_state.authenticated and st.session_state.phone_numbers:
    st.header("4. 🔍 Find Telegram Users")
    
    # Batch size setting
    batch_size = st.slider("Batch Size", min_value=5, max_value=50, value=10, 
                          help="Number of contacts to process at once")
    
    delay = st.slider("Delay between batches (seconds)", min_value=30, max_value=300, value=211,
                     help="Delay to avoid rate limiting")
    
    if st.button("🔍 Start Finding Users", type="primary"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        results_container = st.empty()
        
        st.session_state.found_users = []
        total_batches = (len(st.session_state.phone_numbers) + batch_size - 1) // batch_size
        
        try:
            async def find_users():
                for i in range(0, len(st.session_state.phone_numbers), batch_size):
                    batch_num = i // batch_size + 1
                    batch = st.session_state.phone_numbers[i:i+batch_size]
                    
                    status_text.text(f"Processing batch {batch_num}/{total_batches}...")
                    
                    contacts = [
                        InputPhoneContact(client_id=j, phone=number, first_name='A', last_name='')
                        for j, number in enumerate(batch)
                    ]
                    
                    try:
                        result = await st.session_state.client(ImportContactsRequest(contacts))
                        
                        batch_users = []
                        for user in result.users:
                            user_info = {
                                'first_name': user.first_name or '',
                                'last_name': user.last_name or '',
                                'username': user.username or '',
                                'phone': user.phone or ''
                            }
                            batch_users.append(user_info)
                            st.session_state.found_users.append(user_info)
                        
                        # Update progress
                        progress = min(batch_num / total_batches, 1.0)
                        progress_bar.progress(progress)
                        
                        # Show batch results
                        with results_container.container():
                            if batch_users:
                                st.success(f"Batch {batch_num}: Found {len(batch_users)} users")
                                for user in batch_users:
                                    username_display = f"@{user['username']}" if user['username'] else "No username"
                                    st.text(f"👤 {user['first_name']} {user['last_name']} — {username_display} — {user['phone']}")
                            else:
                                st.info(f"Batch {batch_num}: No users found")
                        
                        # Delay between batches (except for the last batch)
                        if batch_num < total_batches:
                            for remaining in range(delay, 0, -1):
                                status_text.text(f"Waiting {remaining} seconds before next batch...")
                                await asyncio.sleep(1)
                    
                    except FloodWaitError as e:
                        st.warning(f"Rate limit hit. Waiting {e.seconds} seconds...")
                        await asyncio.sleep(e.seconds)
                    except Exception as e:
                        st.error(f"Error in batch {batch_num}: {str(e)}")
            
            # Run the search
            loop = get_or_create_event_loop()
            loop.run_until_complete(find_users())
            
            status_text.text("✅ Search completed!")
            progress_bar.progress(1.0)
            
        except Exception as e:
            st.error(f"❌ Error during search: {str(e)}")

# Step 5: Results and Download
if st.session_state.found_users:
    st.header("5. 📊 Results")
    
    st.success(f"✅ Found {len(st.session_state.found_users)} Telegram users out of {len(st.session_state.phone_numbers)} phone numbers")
    
    # Display results in a nice format
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Found Users:")
        results_df = pd.DataFrame(st.session_state.found_users)
        st.dataframe(results_df, use_container_width=True)
    
    with col2:
        st.subheader("Statistics:")
        st.metric("Total Numbers Checked", len(st.session_state.phone_numbers))
        st.metric("Users Found", len(st.session_state.found_users))
        success_rate = (len(st.session_state.found_users) / len(st.session_state.phone_numbers)) * 100
        st.metric("Success Rate", f"{success_rate:.1f}%")
    
    # Download options
    st.subheader("📥 Download Results")
    
    # Prepare download data
    download_text = []
    for user in st.session_state.found_users:
        username_display = f"@{user['username']}" if user['username'] else "No username"
        line = f"git {user['phone']}"
        download_text.append(line)
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Text file download
        text_content = '\n'.join(download_text)
        st.download_button(
            label="📄 Download as Text File",
            data=text_content,
            file_name="telegram_users_found.txt",
            mime="text/plain"
        )
    
    with col2:
        # Excel file download
        excel_df = pd.DataFrame(st.session_state.found_users)
        excel_buffer = pd.ExcelWriter('temp.xlsx', engine='openpyxl')
        excel_df.to_excel(excel_buffer, index=False)
        excel_buffer.close()
        
        with open('temp.xlsx', 'rb') as f:
            st.download_button(
                label="📊 Download as Excel File",
                data=f.read(),
                file_name="telegram_users_found.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# Cleanup
if st.session_state.client:
    if st.button("🔐 Disconnect", help="Disconnect from Telegram"):
        try:
            async def disconnect_client():
                await st.session_state.client.disconnect()
            
            loop = get_or_create_event_loop()
            loop.run_until_complete(disconnect_client())
            st.session_state.client = None
            st.session_state.authenticated = False
            st.session_state.auth_step = 'start'
            st.success("✅ Disconnected successfully!")
            st.rerun()
        except Exception as e:
            st.error(f"Error disconnecting: {str(e)}")

# Footer
st.markdown("---")
st.markdown("🔒 **Privacy Note**: This app processes phone numbers locally and connects directly to Telegram's API. No data is stored on external servers.")