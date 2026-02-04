import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import requests
import json
import re

# ================= 1. 核心配置 =================
# 依然使用同一个谷歌表格，但只读取基金专属的那一页
SCOPE = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
SHEET_NAME = "Team_Data_Center" 
TAB_NAME = "Fund_Portfolio" # 你的基金数据存在这个分页里

# 北京时间
def get_beijing_time():
    utc = datetime.utcnow()
    bj = utc + timedelta(hours=8)
    return bj.strftime("%Y-%m-%d"), bj.strftime("%H:%M")

# ================= 2. 谷歌连接 & 基金接口 =================
@st.cache_resource
def get_db_connection():
    try:
        # 读取 Secrets
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME)
        return sheet
    except Exception as e:
        return None

# 读取数据
def load_data():
    sh = get_db_connection()
    if not sh: return pd.DataFrame()
    try:
        try:
            worksheet = sh.worksheet(TAB_NAME)
        except:
            # 如果没有这个分页，自动创建
            worksheet = sh.add_worksheet(title=TAB_NAME, rows=100, cols=20)
            worksheet.update([["code", "name", "shares", "avg_cost"]]) # 写入表头
            
        raw = worksheet.get_all_values()
        if not raw: return pd.DataFrame(columns=["code", "name", "shares", "avg_cost"])
        
        headers = raw[0]
        rows = raw[1:]
        df = pd.DataFrame(rows, columns=headers) if rows else pd.DataFrame(columns=headers)
        return df
    except:
        return pd.DataFrame(columns=["code", "name", "shares", "avg_cost"])

# 保存数据
def save_data(df):
    sh = get_db_connection()
    if not sh: return False
    try:
        with st.spinner('☁️ 数据同步中...'):
            try: ws = sh.worksheet(TAB_NAME)
            except: ws = sh.add_worksheet(title=TAB_NAME, rows=100, cols=20)
            ws.clear()
            if df.empty: ws.update([df.columns.values.tolist()])
            else: ws.update([df.columns.values.tolist()] + df.astype(str).values.tolist())
            return True
    except Exception as e:
        st.error(f"保存失败: {e}")
        return False

# 获取实时估值接口
def get_fund_realtime_info(fund_code):
    url = f"http://fundgz.1234567.com.cn/js/{fund_code}.js"
    try:
        r = requests.get(url, timeout=3)
        if r.status_code == 200:
            content = r.text
            match = re.search(r'jsonpgz\((.*?)\);', content)
            if match:
                data = json.loads(match.group(1))
                return {
                    "code": data['fundcode'], "name": data['name'],
                    "nav_date": data['jzrq'], "nav": float(data['dwjz']),
                    "est_val": float(data['gsz']), "est_rate": float(data['gszzl']),
                    "time": data['gztime']
                }
    except: pass
    return None

# ================= 3. 页面主程序 =================
st.set_page_config(page_title="我的私人金库", page_icon="💰", layout="wide")

# 简单密码保护 (防止别人乱入)
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔒 私人资产看板")
    pwd = st.text_input("请输入访问密码", type="password")
    if st.button("解锁"):
        if pwd == "8888": # ⭐ 这里你可以改密码
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("密码错误")
else:
    # --- 正式内容 ---
    bj_date, bj_time = get_beijing_time()
    
    # 顶部栏
    c_title, c_ref = st.columns([3, 1])
    with c_title: st.title(f"💰 基金实盘 ({bj_time})")
    with c_ref: 
        if st.button("🔄 刷新行情", type="primary"): st.rerun()

    # 读取持仓
    fund_df = load_data()
    
    portfolio_data = []
    total_assets = 0.0
    total_profit_day = 0.0
    total_profit_all = 0.0
    
    if not fund_df.empty:
        # 进度条
        progress_text = "正在拉取实时行情..."
        my_bar = st.progress(0, text=progress_text)
        
        for i, row in fund_df.iterrows():
            code = str(row["code"]).zfill(6)
            shares = float(row["shares"] or 0)
            cost = float(row["avg_cost"] or 0)
            
            info = get_fund_realtime_info(code)
            
            if info:
                cur_val = info['est_val']
                hold_amt = shares * cur_val
                day_p = shares * (cur_val - info['nav'])
                all_p = (cur_val - cost) * shares
                
                total_assets += hold_amt
                total_profit_day += day_p
                total_profit_all += all_p
                
                portfolio_data.append({
                    "代码": code, "名称": info['name'],
                    "估值": cur_val, "涨幅": f"{info['est_rate']}%",
                    "份额": shares, "成本": cost,
                    "持仓金额": hold_amt,
                    "今日盈亏": day_p, "总盈亏": all_p,
                    "更新": info['time']
                })
            else:
                # 获取失败保留原始数据
                portfolio_data.append({"代码": code, "名称": row["name"], "估值": "-", "涨幅": "-", "份额": shares, "成本": cost, "持仓金额": 0, "今日盈亏": 0, "总盈亏": 0, "更新": "-"})
            
            my_bar.progress((i + 1) / len(fund_df), text=f"正在更新: {code}")
        
        my_bar.empty()

    # 资产大屏
    m1, m2, m3 = st.columns(3)
    m1.metric("💰 总持仓", f"¥{total_assets:,.2f}")
    m2.metric("📈 今日盈亏", f"¥{total_profit_day:,.2f}", delta=f"{total_profit_day:,.2f}", delta_color="inverse")
    m3.metric("🏆 总盈亏", f"¥{total_profit_all:,.2f}", delta=f"{total_profit_all:,.2f}", delta_color="inverse")
    
    st.divider()

    # 列表展示
    if portfolio_data:
        show_df = pd.DataFrame(portfolio_data)
        st.dataframe(
            show_df, 
            use_container_width=True,
            column_config={
                "今日盈亏": st.column_config.NumberColumn(format="¥%.2f"),
                "总盈亏": st.column_config.NumberColumn(format="¥%.2f"),
                "持仓金额": st.column_config.NumberColumn(format="¥%.2f"),
                "涨幅": st.column_config.TextColumn(help="实时估值涨跌幅"),
            }
        )
    else:
        st.info("还没有持仓，请在下方建仓。")

    st.divider()
    
    # 底部操作区
    tab_add, tab_buy = st.tabs(["➕ 初始建仓", "💰 加仓(自动算成本)"])
    
    with tab_add:
        c1, c2, c3, c4 = st.columns(4)
        n_code = c1.text_input("基金代码", max_chars=6)
        n_shares = c2.number_input("份额", min_value=0.0, step=100.0)
        n_cost = c3.number_input("成本价", min_value=0.0, format="%.4f")
        if c4.button("确认建仓"):
            if n_code and n_shares > 0:
                info = get_fund_realtime_info(n_code)
                name = info['name'] if info else "未知"
                new_row = {"code": n_code, "name": name, "shares": n_shares, "avg_cost": n_cost}
                save_data(pd.concat([fund_df, pd.DataFrame([new_row])], ignore_index=True))
                st.success(f"已添加 {name}")
                time.sleep(1)
                st.rerun()

    with tab_buy:
        if not fund_df.empty:
            c_sel, c_amt, c_nav, c_btn = st.columns(4)
            fund_list = [f"{r['code']} - {r['name']}" for _, r in fund_df.iterrows()]
            sel = c_sel.selectbox("选择基金", fund_list)
            add_amt = c_amt.number_input("加仓金额 (元)", min_value=0.0, step=100.0)
            now_nav = c_nav.number_input("成交净值", min_value=0.0, format="%.4f")
            
            if c_btn.button("确认加仓"):
                code = sel.split(" - ")[0]
                idx = fund_df[fund_df["code"].astype(str) == code].index[0]
                
                old_s = float(fund_df.at[idx, "shares"])
                old_c = float(fund_df.at[idx, "avg_cost"])
                
                add_s = add_amt / now_nav
                new_s = old_s + add_s
                new_c = ((old_s * old_c) + add_amt) / new_s
                
                fund_df.at[idx, "shares"] = new_s
                fund_df.at[idx, "avg_cost"] = new_c
                save_data(fund_df)
                st.success(f"加仓成功！新成本: {new_c:.4f}")
                time.sleep(1)
                st.rerun()
