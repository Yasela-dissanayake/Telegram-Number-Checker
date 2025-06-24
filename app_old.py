import streamlit as st
from telethon.sync import TelegramClient
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.types import InputPhoneContact
import pandas as pd
import asyncio
import nest_asyncio
import os

nest_asyncio.apply()
st.set_page_config(page_title="Telegram Contact Checker", layout="centered")
st.title("📲 Telegram Contact Checker")

# === State Management ===
if "stage" not in st.session_state:
    st.session_state.stage = "input"

# === Step 1: Input Credentials ===
if st.session_state.stage == "input":
    api_id = st.text_input("API ID", type="password")
    api_hash = st.text_input("API Hash", type="password")
    phone = st.text_input("Phone Number (e.g., +91XXXXXXXXXX)")
    file = st.file_uploader("Upload Excel File (.xlsx with 'Mobile Number' column)", type=["xlsx"])

    if api_id and api_hash and phone and file:
        try:
            st.session_state.api_id = int(api_id)
            st.session_state.api_hash = api_hash
            st.session_state.phone = phone
            st.session_state.file = file
            st.session_state.session_name = f"session_{phone.replace('+', '')}"

            # Clear old session
            for ext in ["", ".session-journal", ".session-wal", ".session-shm"]:
                try:
                    os.remove(f"{st.session_state.session_name}{ext}")
                except FileNotFoundError:
                    pass

            st.session_state.stage = "otp_input"
            st.rerun()
        except Exception as e:
            st.error(f"❌ Setup Error: {e}")

# === Step 2: OTP Input ===
elif st.session_state.stage == "otp_input":
    st.info("📨 You'll receive an OTP on your Telegram account.")
    otp_code = st.text_input("Enter OTP Code (once you receive it)", type="password")

    if "client" not in st.session_state:
        st.session_state.client = TelegramClient(
            st.session_state.session_name,
            st.session_state.api_id,
            st.session_state.api_hash
        )

    client = st.session_state.client

    async def start_login():
        await client.connect()

        try:
            if otp_code:
                await client.start(
                    phone=st.session_state.phone,
                    code_callback=lambda: otp_code
                )
                st.success("✅ Logged in successfully.")
                st.session_state.stage = "process"
                st.rerun()
            else:
                st.warning("✋ Please wait until you receive and enter the OTP.")

        except SessionPasswordNeededError:
            st.session_state.stage = "password"
            st.rerun()
        except Exception as e:
            st.error(f"❌ Login Error: {e}")

    asyncio.run(start_login())

# === Step 3: 2FA Password (if needed) ===
elif st.session_state.stage == "password":
    password = st.text_input("🔒 Enter your Telegram 2FA Password", type="password")
    if st.button("Submit Password"):
        async def password_login():
            try:
                await st.session_state.client.sign_in(password=password)
                st.success("✅ Logged in with 2FA.")
                st.session_state.stage = "process"
                st.rerun()
            except Exception as e:
                st.error(f"❌ 2FA Error: {e}")
        asyncio.run(password_login())

# === Step 4: Process Contacts ===
elif st.session_state.stage == "process":
    st.info("🔍 Importing contacts and checking for Telegram users...")

    async def run():
        client = st.session_state.client
        await client.start()

        df = pd.read_excel(st.session_state.file)
        raw_numbers = df["Mobile Number"].astype(str)

        phone_numbers = [
            "+91" + ''.join(filter(str.isdigit, num))[-10:]
            for num in raw_numbers if len(''.join(filter(str.isdigit, num))) >= 10
        ]
        phone_numbers = list(set(phone_numbers))

        found_users = []
        uid = 0

        for i in range(0, len(phone_numbers), 10):
            batch = phone_numbers[i:i+10]
            contacts = [
                InputPhoneContact(client_id=uid + j, phone=phone, first_name="A", last_name="")
                for j, phone in enumerate(batch)
            ]
            uid += len(batch)

            try:
                result = await client(ImportContactsRequest(contacts))
                for user in result.users:
                    info = f"{user.first_name or ''} {user.last_name or ''} — @{user.username or 'N/A'} — {user.phone}"
                    found_users.append(info)
                await asyncio.sleep(15)
            except FloodWaitError as e:
                st.warning(f"⏳ Flood wait for {e.seconds}s...")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                st.error(f"❌ Batch error: {e}")
                continue

        await client.disconnect()

        result_text = "\n".join(found_users)
        with open("found_users.txt", "w", encoding="utf-8") as f:
            f.write(result_text)

        st.success(f"✅ Found {len(found_users)} Telegram users.")
        st.download_button("📄 Download Results", result_text, file_name="found_users.txt")

    asyncio.run(run())
