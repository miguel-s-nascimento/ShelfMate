import streamlit as st
import time
from dotenv import load_dotenv
from chatbot.bot import MainChatbot  # Import the chatbot class
import sqlitecloud  
# Load environment variables
load_dotenv()

# Function to check authentication
def check_auth():
    return 'logged_in' in st.session_state and st.session_state.logged_in

# Function to simulate streaming response
def simulate_streaming(message):
    buffer = ""
    for char in message:
        buffer += char
        if char in [" ", "\n"]:
            yield buffer.strip() + ("<br>" if char == "\n" else " ")
            buffer = ""
            time.sleep(0.1 if char == "\n" else 0.05)
    if buffer:
        yield buffer

# Function to get user conversation_id from the database
def get_user_conversation_id(username):
    conn = sqlitecloud.connect("sqlitecloud://cikwryuhhz.g6.sqlite.cloud:8860/shelfmate.db?apikey=fxZSlHTpxWU109u7go8avF2RRHsZ43JUxDfarjdFpYg")  # Path to your SQLite database
    cursor = conn.cursor()
    cursor.execute("SELECT conversation_id FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return 0  # Return 0 if the user does not exist

# Authentication check
if not check_auth():
    st.warning("You need to login to access the chatbot.")
    if st.button("Go to Login Page"):
        st.switch_page("pages/Login.py")  # Assuming you have a login page
else:
    st.title("ShelfMate Chatbot")

    username = st.session_state['username']

    # Get the conversation_id from the database
    conversation_id = get_user_conversation_id(username)

    # First-time user check
    if conversation_id == 1:
        # Show first-time user message
        first_time_message = f"""
        Hello, {username}! 👋
        
        Welcome to ShelfMate—your go-to app for discovering your next favorite book! 📚
        
        Before we begin, let’s set up your reading profile to ensure you get the best suggestions:
        
        1. Share your favorite authors and genres. 
        2. Add books you’re currently reading or have already read to your Read List, and be sure to specify if they’re In Progress/Finished, or Not Finished. Don’t forget to rate them from 1 to 5 stars (⭐) so we can better understand your preferences.
        
        Whenever you’re ready, you can also ask me about our collection of available books, genres, or authors. I’m here to help you explore!
        
        Let’s get reading!🚀"""
        
        st.session_state.messages = [{"role": "assistant", "content": first_time_message}]
    

    if conversation_id >= 2:
        # Show welcome back message
        welcome_back_message = f"Welcome back, {username}! 👋 It's great to see you again. How can I assist you today?"
        st.session_state.messages = [{"role": "assistant", "content": welcome_back_message}]

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        avatar = "👤" if message["role"] == "user" else "images/corujafofa.jpg"
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])

    # Accept user input
    if user_input := st.chat_input("Chat with ShelfMate"):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)

        # Initialize the chatbot instance
        bot = MainChatbot()
        bot.user_login(username=username, conversation_id=conversation_id)

        with st.spinner('Thinking...'):
            try:
                # Process user input using the bot
                response = bot.process_user_input({"user_input": user_input})
                with st.chat_message("assistant", avatar="images/corujafofa.jpg"):
                    st.markdown(response, unsafe_allow_html=True)
                # Add assistant response to chat history
                st.session_state.messages.append({"role": "assistant", "content": response})
            except Exception as e:
                st.error(f"Error: {str(e)}")