import datetime
import re
import sqlitecloud
import time

import streamlit as st

db_path = "sqlitecloud://cikwryuhhz.g6.sqlite.cloud:8860/shelfmate.db?apikey=fxZSlHTpxWU109u7go8avF2RRHsZ43JUxDfarjdFpYg"
conn = sqlitecloud.connect(db_path)
cursor = conn.cursor()


def check_email_exists(email):
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM users WHERE email = ?", (email,))
    output = cursor.fetchone() is not None
    return output


st.markdown(
        """
        <style>
        @keyframes bounce {
            0%, 20%, 50%, 80%, 100% {
                transform: translateY(0);
            }
            40% {
                transform: translateY(-10px);
            }
            60% {
                transform: translateY(-5px);
            }
        }
        .animated-title {
            font-size: 45px;
            font-weight: 800;
            text-align: center;
            animation: bounce 2s infinite;
        }
        </style>
        <div class="animated-title">Register here!</div>
        """,
        unsafe_allow_html=True
    )

st.markdown("<br>", unsafe_allow_html=True)
st.write("Fill in the form below to register and have access to our chatbot!")
st.markdown("<br>", unsafe_allow_html=True)


with st.form("registration_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        name = st.text_input("Name")
        email = st.text_input("Email")
        district = st.selectbox("District", ["Select", "Aveiro",
                                    "Beja",
                                    "Braga",
                                    "Bragança",
                                    "Castelo Branco",
                                    "Coimbra",
                                    "Évora",
                                    "Faro",
                                    "Guarda",
                                    "Leiria",
                                    "Lisboa",
                                    "Portalegre",
                                    "Porto",
                                    "Santarém",
                                    "Setúbal",
                                    "Viana do Castelo",
                                    "Vila Real",
                                    "Viseu",
                                    "Açores",
                                    "Madeira"])
    
    
    with col2:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        gender = st.selectbox("Gender", ["Select", "Male", "Female", "Other"])
       
        
    if st.form_submit_button("Register"):
        if check_email_exists(email):
            st.error("Email already registered!")
        else:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (name, email, district, username,password,gender) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, (name, email, district, username,password,gender))
            conn.commit()
            st.success("Registration successful!")
            time.sleep(1)
            st.switch_page("pages/Login.py")

conn.close()