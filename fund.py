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
SCOPE = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
SHEET_NAME = "Team_Data_Center" 
TAB_NAME = "Fund_Portfolio" 

def get_beijing_time():
    utc = datetime.utcnow()
    bj = utc + timedelta(hours=8)
    return bj.strftime("%Y-%m-%d"), bj.strftime("%H:%M")

# ================= 2. 谷歌连接 & 数据接口 =================
@st.cache_resource
def get_db_connection():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME)
        return sheet
    except Exception as e: return None

def load_data():
    sh = get_db_connection()
    if not sh: return pd.DataFrame()
    try:
        try: worksheet = sh.worksheet(TAB_NAME)
        except: 
            worksheet = sh.add_worksheet(title=TAB_NAME, rows=100, cols=20)
            worksheet.update([["code", "name", "shares", "avg_cost", "proxy_code"]]) 
        
        raw = worksheet.get_all_values()
        if not raw: return pd.DataFrame(columns=["code", "name", "shares", "avg_cost", "proxy_code"])
        
        headers = raw[0]
        if "proxy_code" not in headers:
            headers.append("proxy_code")
            rows = raw[1:]
            df = pd.DataFrame(rows, columns=raw[0])
            df["proxy_code"] = ""
            return df
            
        rows = raw[1:]
        df = pd.DataFrame(rows, columns=headers) if rows else pd.DataFrame(columns=headers)
        return df
    except: return pd.DataFrame()

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
    except: return False

# --- 接口1: 获取基金官方净值 (用于盘后) ---
def get_official_nav(fund_code):
    # 使用天天基金接口获取最新的确切净值 (非估值)
    url = f"http://fundgz.1234567.com.cn/js/{fund_code}.js"
    try:
        r = requests.get(url, timeout=2)
        if r.status_code == 200:
            content = r.text
            match = re.search(r'jsonpgz\((.*?)\);', content)
            if match:
                data = json.loads(match.group(1))
                return {
                    "nav": float(data['dwjz']),      # 确切净值 (通常是昨天的，更新后是今天的)
                    "date": data['jzrq'],            # 净值日期 (关键判断依据)
                    "name": data['name']
                }
    except: pass
    return None

# --- 接口2: 获取影子ETF实时涨跌 (用于盘中) ---
def get_proxy_rate(proxy_code):
    if not proxy_code or len(proxy_code) < 6: return 0.0
    url = f"http://hq.sinajs.cn/list={proxy_code}"
    try:
        headers = {"Referer": "https://finance.sina.com.cn"}
        r = requests.get(url, headers=headers, timeout=2)
        if r.status_code == 200:
            data = r.text.split(",")
            if len(data) > 3:
                yesterday = float(data[2])
                current = float(data[3])
                if current == 0: current = yesterday # 没开盘
                if yesterday == 0: return 0.0
                return ((current - yesterday) / yesterday) * 100
    except: pass
    return 0.0

# ================= 3. 页面主程序 =================
st.set_page_config(page_title="智能资产看板", page_icon="📈", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔒 私人资产看板")
    pwd = st.text_input("请输入访问密码", type="password")
    if st.button("解锁"):
        if pwd == "8888": 
            st.session_state.auth = True
            st.rerun()
        else: st.error("密码错误")
else:
    bj_date, bj_time = get_beijing_time()
    
    # --- 标题栏 ---
    c_title, c_ref = st.columns([3, 1])
    with c_title: st.subheader(f"📈 智能资产看板 ({bj_time})")
    with c_ref: 
        if st.button("🔄 刷新最新数据", type="primary"): st.rerun()

    # --- 读取数据 ---
    fund_df = load_data()
    
    # 汇总变量
    total_market_value = 0.0  # 总持仓市值
    total_cost_value = 0.0    # 总投入本金
    total_day_profit = 0.0    # 今日总盈亏
    
    table_data = []

    if not fund_df.empty:
        # 遍历每一只基金
        for i, row in fund_df.iterrows():
            code = str(row["code"]).zfill(6)
            proxy = str(row["proxy_code"]).strip()
            shares = float(row["shares"] or 0)
            avg_cost = float(row["avg_cost"] or 0)
            
            # 1. 获取官方基础数据 (净值)
            official_info = get_official_nav(code)
            
            nav_base = avg_cost # 默认回退
            nav_date = "未知"
            fund_name = row["name"]
            
            if official_info:
                nav_base = official_info['nav'] # 昨天的确切净值
                nav_date = official_info['date']
                fund_name = official_info['name']
            
            # 2. 智能判断逻辑 (核心!)
            # 逻辑：如果官方净值日期 == 今天，说明收盘数据已出，用官方。
            #       否则，说明还在盘中或数据没更，用影子ETF估算。
            
            is_official_updated = (nav_date == bj_date)
            
            real_price = 0.0
            day_rate = 0.0
            day_profit = 0.0
            
            data_source_label = "" # 标记数据来源
            
            if is_official_updated:
                # === 模式B：官方数据已出 ===
                data_source_label = "✅ 已收录 (官方)"
                real_price = nav_base # 此时 nav_base 已经是今天的净值了
                # 计算今日涨跌 (稍微麻烦点，因为接口只给了今天净值，没给昨天。我们倒推一下)
                # 这里为了简化，如果官方已出，我们假设涨幅显示为 "已更新"，或者尝试计算
                # 实际上 1234567 接口在更新当晚，会保留 gszzl (估算涨幅)，我们可以暂时忽略涨幅显示，只看最终盈亏
                # 或者：如果不存储昨天的净值，很难算出精确的“今日”涨幅。
                # 妥协方案：显示 "-"，但市值和总盈亏是绝对准确的。
                
                day_rate = 0.0 # 难获取，暂置0
                day_profit = 0.0 # 难获取今日单日，但总盈亏是准的
                
                # 重新计算总盈亏逻辑：
                # 既然官方数据出了，我们更关心【总市值】准不准
            else:
                # === 模式A：影子估算 (盘中) ===
                data_source_label = f"⚡ 影子预估 ({proxy})" if proxy else "⚠️ 无影子"
                
                # 获取影子涨幅
                proxy_rate = get_proxy_rate(proxy)
                day_rate = proxy_rate
                
                # 计算：今日预估价 = 昨天净值 * (1 + 影子涨幅)
                real_price = nav_base * (1 + day_rate/100)
                
                # 计算：今日盈亏 = (今日预估价 - 昨天净值) * 份额
                day_profit = (real_price - nav_base) * shares

            # 3. 汇总计算
            market_val = real_price * shares
            cost_val = avg_cost * shares
            total_profit = market_val - cost_val
            
            # 累加总数
            total_market_value += market_val
            total_cost_value += cost_val
            total_day_profit += day_profit
            
            # 颜色处理
            rate_color = "🔴" if day_rate > 0 else "Hz" if day_rate < 0 else "⚪"
            
            # 构造表格行
            table_data.append({
                "基金名称": f"{fund_name}\n({code})",
                "数据源": data_source_label,
                "📊 今日涨幅": f"{day_rate:+.2f}%",
                "💰 今日估值": f"¥{real_price:.4f}",
                "⚡ 今日盈亏": day_profit,  # 数字类型方便后面格式化
                "持仓市值": market_val,
                "总盈亏": total_profit,
                "持有收益率": f"{(total_profit/cost_val)*100:.2f}%" if cost_val>0 else "0%"
            })

    # --- 资产驾驶舱 (优化版) ---
    # 计算总收益率
    total_return_rate = (total_market_value - total_cost_value) / total_cost_value * 100 if total_cost_value > 0 else 0
    
    st.markdown("### 🏦 全局资产概览")
    
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("💰 总持仓市值", f"¥{total_market_value:,.2f}", help="当前所有基金的预估总价值")
    k2.metric("⚡ 今日预估盈亏", f"¥{total_day_profit:,.2f}", delta=f"{total_day_profit:,.2f}", delta_color="inverse", help="基于影子ETF涨幅计算的今日波动")
    k3.metric("🏆 累计总盈亏", f"¥{(total_market_value - total_cost_value):,.2f}", delta=f"{(total_market_value - total_cost_value):,.2f}", delta_color="inverse")
    k4.metric("📈 总收益率", f"{total_return_rate:+.2f}%", delta_color="off")

    st.divider()

    # --- 持仓明细表 ---
    if table_data:
        df_show = pd.DataFrame(table_data)
        st.dataframe(
            df_show,
            use_container_width=True,
            column_config={
                "数据源": st.column_config.TextColumn(help="显示是基于影子代码估算，还是官方已更新数据"),
                "📊 今日涨幅": st.column_config.TextColumn(help="基于影子ETF的实时涨跌幅"),
                "💰 今日估值": st.column_config.TextColumn(help="昨天净值 × (1+影子涨幅)"),
                "⚡ 今日盈亏": st.column_config.NumberColumn(format="¥%.2f", help="今日波动带来的金额变化"),
                "持仓市值": st.column_config.NumberColumn(format="¥%.2f"),
                "总盈亏": st.column_config.NumberColumn(format="¥%.2f", help="当前市值 - 投入本金"),
                "持有收益率": st.column_config.TextColumn(),
            },
            hide_index=True
        )
    else:
        st.info("暂无持仓，请在下方添加。")

    st.divider()

    # --- 操作区 ---
    with st.expander("➕ 添加/修改基金 (记得绑定影子代码!)", expanded=False):
        c1, c2, c3, c4, c5 = st.columns(5)
        n_code = c1.text_input("基金代码", max_chars=6)
        n_name = c2.text_input("名称 (选填)")
        n_proxy = c3.text_input("影子代码 (关键)", placeholder="如 sh510300")
        n_shares = c4.number_input("份额", step=100.0, format="%.2f")
        n_cost = c5.number_input("成本价", format="%.4f")
        
        if st.button("💾 保存/更新数据"):
            if n_code:
                existing = fund_df[fund_df["code"] == n_code]
                if not existing.empty:
                    idx = existing.index[0]
                    fund_df.at[idx, "name"] = n_name
                    fund_df.at[idx, "proxy_code"] = n_proxy
                    fund_df.at[idx, "shares"] = n_shares
                    fund_df.at[idx, "avg_cost"] = n_cost
                else:
                    new_row = {"code": n_code, "name": n_name, "shares": n_shares, "avg_cost": n_cost, "proxy_code": n_proxy}
                    fund_df = pd.concat([fund_df, pd.DataFrame([new_row])], ignore_index=True)
                save_data(fund_df)
                st.success("保存成功")
                time.sleep(1)
                st.rerun()

    with st.expander("🗑️ 删除基金"):
        if not fund_df.empty:
            d_code = st.selectbox("选择删除对象", fund_df["code"].tolist())
            if st.button("确认删除"):
                fund_df = fund_df[fund_df["code"] != d_code]
                save_data(fund_df)
                st.rerun()
