import streamlit as st
import yfinance as yf
import openai
import sqlite3
import base64
import pandas_ta as ta
import pandas as pd
import os
import re
import logging
import matplotlib.pyplot as plt
import mplfinance as mpf
from datetime import datetime
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# 設定 OpenAI API 金鑰
openai.api_key = 'sk-proj-6BnNXUlmhSfAt6cpZUndT3BlbkFJ65y61xtRme75w3KYBQR4'

# 初始化資料庫
conn = sqlite3.connect('stocktest.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users
             (username TEXT PRIMARY KEY, password TEXT, credits INTEGER DEFAULT 0)''')
c.execute('''CREATE TABLE IF NOT EXISTS credit_history
             (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, change INTEGER, reason TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
c.execute('''CREATE TABLE IF NOT EXISTS query_history
             (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, stock_code TEXT, query_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, result_summary TEXT, stock_info TEXT)''')
# c.execute("ALTER TABLE query_history ADD COLUMN stock_info TEXT")

conn.commit()

# Logging 配置
logging.basicConfig(level=logging.INFO)

#將本地圖片轉換為Base64
def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

img_path = "股票封面照.png"
if os.path.exists(img_path):
    img_base64 = get_base64_of_bin_file(img_path)
    page_bg_img = f'''
    <style>
    .stApp {{
      background-image: url("data:image/jpg;base64,{img_base64}");
      background-size: cover;
    }}
    </style>
    '''
    st.markdown(page_bg_img, unsafe_allow_html=True)
else:
    st.error('圖片路徑無效或圖片不存在')

# 更新用戶點數並返回剩餘點數
def update_credits(username, amount, reason):
    remaining_credits = 0
    try:
        with sqlite3.connect('stocktest.db') as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET credits = credits + ? WHERE username = ?', (amount, username))
            cursor.execute('INSERT INTO credit_history (username, change, reason) VALUES (?, ?, ?)', (username, amount, reason))
            conn.commit()
            cursor.execute('SELECT credits FROM users WHERE username = ?', (username,))
            remaining_credits = cursor.fetchone()[0]
        logging.info(f"Updated credits for user {username}: {amount} for reason: {reason}")
    except sqlite3.Error as e:
        logging.error(f"Error updating credits: {e}")
        st.error(f"Error: {e}")
    return remaining_credits

# 通知用戶
def notify_user(username, subject, message):
    try:
        with sqlite3.connect('stocktest.db') as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT email FROM users WHERE username = ?', (username,))
            email = cursor.fetchone()[0]  # 這裡假設您的資料庫中有 email 的欄位，請自行調整
    except sqlite3.Error as e:
        logging.error(f"Error notifying user: {e}")
        st.error(f"Error: {e}")

# 驗證信用卡號
def validate_card_number(card_number):
    return re.fullmatch(r'^[0-9]{16}$', card_number) is not None

# 驗證到期日
def validate_expiry_date(expiry_date):
    return re.fullmatch(r'^(0[1-9]|1[0-2])\/[0-9]{2}$', expiry_date) is not None

# 驗證 CVV
def validate_cvv(cvv):
    return re.fullmatch(r'^[0-9]{3}$', cvv) is not None

# 登入功能
def login(username, password):
    try:
        c.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password))
        if c.fetchone():
            st.session_state['username'] = username
            st.session_state['logged_in'] = True
        else:
            st.error('帳號或密碼錯誤')
    except sqlite3.Error as e:
        logging.error(f"Error during login: {e}")
        st.error(f"Error: {e}")

# 註冊功能
def register(username, password):
    try:
        c.execute('SELECT * FROM users WHERE username = ?', (username,))
        if c.fetchone():
            st.error('帳號已存在')
        else:
            # 將預設點數設為 10
            c.execute('INSERT INTO users (username, password, credits) VALUES (?, ?, ?)', (username, password, 10))
            conn.commit()
            st.success('註冊成功，請登入')
    except sqlite3.Error as e:
        logging.error(f"Error during registration: {e}")
        st.error(f"Error: {e}")

# 忘記密碼功能
def forgot_password(username):
    try:
        c.execute('SELECT password FROM users WHERE username = ?', (username,))
        result = c.fetchone()
        if result:
            st.info(f'您的密碼是：{result[0]}')
        else:
            st.error('帳號不存在')
    except sqlite3.Error as e:
        logging.error(f"Error during password retrieval: {e}")
        st.error(f"Error: {e}")


# 建立登入狀態
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# 主要應用程式
if not st.session_state['logged_in']:
    st.title('歡迎光臨股票資訊APP')
    st.title('請登入')
    page = st.selectbox('選擇操作', ['登入', '註冊', '忘記密碼'])

    if page == '登入':
        username = st.text_input('帳號')
        password = st.text_input('密碼', type='password')
        if st.button('登入'):
            login(username, password)

    elif page == '註冊':
        username = st.text_input('帳號')
        password = st.text_input('密碼', type='password')
        if st.button('註冊'):
            register(username, password)

    elif page == '忘記密碼':
        username = st.text_input('帳號')
        if st.button('找回密碼'):
            forgot_password(username)

else:
    # 右側欄位
    with st.sidebar:
        st.header('功能表')
        page = st.radio('選擇頁面', ['主頁面', '儲值', '歷史查詢', '點數歷史'])

        # 添加登出按鈕
        if st.button('登出'):
            st.session_state['logged_in'] = False
            st.session_state.pop('username', None)
            st.success('成功登出！')

    # 主頁面
    if page == '主頁面':
        st.title('股票資訊')

        # 輸入股票代號（或其他相關資訊）
        stock_code = st.text_input('台股請輸入股票代號+.TW（例如：2330.TW）')
        
        # 將查詢歷史記錄到資料庫
        try:
            with sqlite3.connect('stocktest.db') as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO query_history (username, stock_code, query_date) VALUES (?, ?, ?)',
                               (st.session_state['username'], stock_code, datetime.now()))
                conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Error saving query history: {e}")
            st.error(f"Error: {e}")


        # 檢查是否有輸入股票代號
        if stock_code:
            # 檢查剩餘點數是否足夠
            remaining_credits = update_credits(st.session_state['username'], 0, '查詢股票資訊')
            if remaining_credits < 1:
                st.error('點數不足，請儲值後再進行股票資訊查詢。')
            else:
                # 使用 yfinance 獲取股票資訊
                stock = yf.Ticker(stock_code)

                # 獲取最近5個交易日的股票歷史資料
                history = stock.history(period='1mo')

                # 顯示剩餘點數
                remaining_credits = update_credits(st.session_state['username'], -1, '查詢股票資訊')
                st.info(f'剩餘點數：{remaining_credits}')

                # 顯示股票資訊
                if not history.empty:
                    st.write(f'### {stock_code} 的最近30個交易日資訊')
                    st.write(history[::-1])

                    # 繪製K線圖
                    st.write(f'### {stock_code} 的K線圖')
                    fig, ax = plt.subplots(figsize=(10, 5))
                    mpf.plot(history, type='candle', ax=ax)
                    st.pyplot(fig)

                    # 顯示近一年的財務報表、估值和技術指標
                    st.write(f'### {stock_code} 的財務報表、估值和技術指標')

                    # 財務報表
                    st.write('#### 財務報表')
                    financials = stock.financials
                    st.write(financials)

                    # 獲取財務報表
                    st.write('#### 資產負債表')
                    st.write(stock.balance_sheet)
                    st.write('#### 損益表')
                    st.write(stock.financials)
                    st.write('#### 現金流量表')
                    st.write(stock.cashflow)

                    # 估值
                    st.write('#### 估值')
                    valuation_measures = stock.info
                    # 將估值數據轉換為 DataFrame 格式
                    data = {
                        "指標": ["本益比 (P/E Ratio)", "股價營收比 (P/S Ratio)", "市值", "每股收益 (EPS, TTM)"],
                        "數值": [
                            valuation_measures.get('trailingPE', 'N/A'),
                            valuation_measures.get('priceToSalesTrailing12Months', 'N/A'),
                            valuation_measures.get('marketCap', 'N/A'),
                            valuation_measures.get('trailingEps', 'N/A')
                        ]
                    }

                    df = pd.DataFrame(data)

                    # 使用 st.table 顯示表格
                    st.table(df)

                    # 或使用 st.dataframe 顯示表格
                    # st.dataframe(df)
                    # 使用 OpenAI API 分析股票代號
                    prompt = f"請先介紹股票代號 {stock_code} 的公司介紹，再根據所顯示股票資訊與財務報表{financials}、估值{valuation_measures}來分析股票代號 {stock_code} 近期走勢和未來預測，並用股票名稱+股票代號回答"

                    # 調整為 v1/chat/completions endpoint 的使用方式
                    response = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "assistant", "content": "您是一個股票分析師。"},
                            {"role": "user", "content": prompt}
                        ]
                    )

                    # 獲取並顯示分析結果 
                    analysis_result = response['choices'][0]['message']['content'].strip()
                    st.write('### 分析結果：')
                    st.write(analysis_result)


                    # 新增與 GPT-3 對話的區塊
                    st.subheader('與 小助手 對話')
                    user_input = st.text_area('請輸入您的問題或對話：', '')
                    if user_input:
                        # 調整為 v1/chat/completions endpoint 的使用方式
                        response = openai.ChatCompletion.create(
                            model="gpt-3.5-turbo",
                            messages=[
                                {"role": "user", "content": user_input}
                            ]
                        )
                        answer = response['choices'][0]['message']['content'].strip()
                        st.write('小助手 的回答：')
                        st.write(answer)

                else:
                    st.write('找不到此股票的資訊。請確認股票代號是否正確。')

    elif page == '儲值':
        st.title('儲值')
        st.subheader('儲值點數')
        st.write('信用卡儲值：')

        card_number = st.text_input('信用卡號')
        expiry_date = st.text_input('到期日（MM/YY）')
        cvv = st.text_input('CVV', type='password')
        amount = st.number_input('輸入儲值金額', min_value=1, max_value=100)

        if st.button('儲值'):
            if not validate_card_number(card_number):
                st.error('無效的信用卡號')
            elif not validate_expiry_date(expiry_date):
                st.error('無效的到期日，格式應為MM/YY')
            elif not validate_cvv(cvv):
                st.error('無效的CVV，應為三位數字')
            else:
                update_credits(st.session_state['username'], amount, '儲值')
                st.success(f'成功增加 {amount} 點數！')


    elif page == '歷史查詢':
        st.title('查詢歷史')


        # 查詢並顯示有效的查詢歷史記錄
        try:
            with sqlite3.connect('stocktest.db') as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT stock_code, query_date FROM query_history WHERE username = ? AND stock_code <> "" ORDER BY query_date DESC', (st.session_state['username'],))
                query_history = cursor.fetchall()

                if query_history:
                    st.write('### 查詢歷史')
                    for record in query_history:
                        st.write(f'- 股票代號：{record[0]}, 查詢時間：{record[1]}')
                else:
                    st.info('您還沒有進行過有效的查詢。')
        except sqlite3.Error as e:
            logging.error(f"Error fetching query history: {e}")
            st.error(f"Error: {e}")


    
    elif page == '點數歷史':
        st.title('點數歷史')
        st.subheader('點數變化記錄')
        try:
            with sqlite3.connect('stocktest.db') as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT change, reason, timestamp FROM credit_history WHERE username = ? AND change != 0 ORDER BY timestamp DESC', (st.session_state['username'],))
                history = cursor.fetchall()

                if history:
                    for change, reason, timestamp in history:
                        st.write(f"{timestamp}: {reason} - 點數變化: {change}")
                else:
                    st.info('您還沒有進行過有效的點數變化。')
        except sqlite3.Error as e:
            logging.error(f"Error fetching credit history: {e}")
            st.error(f"Error: {e}")

        
